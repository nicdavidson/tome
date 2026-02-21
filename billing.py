"""Stripe billing integration for Tome.

Handles checkout sessions, webhook events, and subscription management.
"""
import hmac
import hashlib
import json
import logging
import httpx
from config import Config

log = logging.getLogger("tome.billing")

API = "https://api.stripe.com/v1"


def _headers():
    return {"Authorization": f"Bearer {Config.STRIPE_SECRET_KEY}"}


async def create_checkout_session(plan: str, customer_email: str = None) -> dict:
    """Create a Stripe Checkout session for a subscription."""
    price_id = Config.STRIPE_PRICES.get(plan)
    if not price_id:
        raise ValueError(f"Unknown plan: {plan}")

    data = {
        "mode": "subscription",
        "payment_method_types[]": "card",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": f"{Config.BASE_URL}/welcome?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{Config.BASE_URL}/#pricing",
        "subscription_data[trial_period_days]": "14",
    }
    if customer_email:
        data["customer_email"] = customer_email

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{API}/checkout/sessions",
            headers=_headers(),
            data=data,
        )
        resp.raise_for_status()
        return resp.json()


async def get_session(session_id: str) -> dict:
    """Retrieve a checkout session."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API}/checkout/sessions/{session_id}",
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def create_portal_session(customer_id: str) -> dict:
    """Create a Stripe Customer Portal session for managing subscriptions."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{API}/billing_portal/sessions",
            headers=_headers(),
            data={
                "customer": customer_id,
                "return_url": f"{Config.BASE_URL}/dashboard",
            },
        )
        resp.raise_for_status()
        return resp.json()


def verify_webhook_signature(payload: bytes, sig_header: str) -> bool:
    """Verify Stripe webhook signature."""
    if not Config.STRIPE_WEBHOOK_SECRET:
        return True  # skip in dev

    try:
        elements = dict(item.split("=", 1) for item in sig_header.split(","))
        timestamp = elements.get("t", "")
        signature = elements.get("v1", "")

        signed_payload = f"{timestamp}.{payload.decode()}"
        expected = hmac.new(
            Config.STRIPE_WEBHOOK_SECRET.encode(),
            signed_payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


async def handle_webhook_event(event: dict):
    """Process a Stripe webhook event."""
    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        stripe_customer_id = data.get("customer", "")
        email = data.get("customer_email", "") or data.get("customer_details", {}).get("email", "")
        subscription_id = data.get("subscription", "")
        log.info("New subscription: customer=%s email=%s sub=%s", stripe_customer_id, email, subscription_id)

        import db
        # Check if customer already exists (from onboarding)
        existing = db.get_customer_by_email(email) if email else None
        if existing:
            conn = db.get_db()
            conn.execute(
                "UPDATE customers SET stripe_customer_id = ?, stripe_subscription_id = ? WHERE id = ?",
                (stripe_customer_id, subscription_id, existing["id"])
            )
            conn.commit()
            conn.close()
        else:
            db.create_customer(
                email=email,
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=subscription_id,
            )

    elif event_type == "customer.subscription.deleted":
        subscription_id = data.get("id", "")
        log.info("Subscription cancelled: %s", subscription_id)
        import db
        conn = db.get_db()
        conn.execute(
            "UPDATE customers SET status = 'cancelled' WHERE stripe_subscription_id = ?",
            (subscription_id,)
        )
        conn.commit()
        conn.close()

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer", "")
        log.warning("Payment failed for customer: %s", customer_id)

    else:
        log.debug("Unhandled Stripe event: %s", event_type)
