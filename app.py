"""Tome API — autonomous documentation maintenance.

Routes:
  GET  /                         Landing page
  GET  /api/health               Health check
  GET  /api/stats                Overall stats
  POST /api/projects             Create project
  GET  /api/projects             List projects
  GET  /api/projects/{id}        Project details
  GET  /api/projects/{id}/activity  Activity log
  GET  /api/projects/{id}/gaps   Documentation gaps
  POST /api/projects/{id}/scan   Trigger full repo scan
  POST /api/webhook/github       GitHub webhook receiver
"""
import asyncio
import hashlib
import hmac
import json
import logging
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from config import Config
from db import (init_db, create_project, get_project, list_projects, log_activity,
                get_activity, get_gaps, get_stats, verify_api_key,
                create_customer, get_customer_by_email, update_customer_github_token,
                link_project_to_customer, get_customer_projects)
import engine
import github_client as gh
import billing

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("tome")

app = FastAPI(title="Tome", description="Autonomous documentation maintenance", version="0.1.0")


@app.on_event("startup")
async def startup():
    init_db()
    log.info("Tome started on port %d", Config.PORT)


# --- Landing page ---

@app.get("/", response_class=HTMLResponse)
async def landing():
    try:
        with open(f"{Config.STATIC_DIR}/index.html") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>Tome</h1><p>Landing page not found.</p>")


# --- SEO ---

@app.get("/robots.txt")
async def robots():
    return JSONResponse(
        content="User-agent: *\nAllow: /\nSitemap: https://tomehq.net/sitemap.xml",
        media_type="text/plain"
    )

@app.get("/sitemap.xml")
async def sitemap():
    return JSONResponse(
        content="""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://tomehq.net/</loc><priority>1.0</priority></url>
  <url><loc>https://tomehq.net/terms</loc><priority>0.3</priority></url>
  <url><loc>https://tomehq.net/privacy</loc><priority>0.3</priority></url>
</urlset>""",
        media_type="application/xml"
    )


# --- Legal pages ---

@app.get("/terms", response_class=HTMLResponse)
async def terms():
    return HTMLResponse(_legal_page("Terms of Service", """
<p><strong>Last updated:</strong> February 20, 2026</p>
<p>These Terms of Service govern your use of Tome ("the Service"), operated by Tome HQ.</p>

<h2>1. Service Description</h2>
<p>Tome is an autonomous documentation maintenance service that monitors code repositories and generates documentation updates via pull requests.</p>

<h2>2. Account Terms</h2>
<p>You must provide a valid email address and GitHub account to use the Service. You are responsible for maintaining the security of your account credentials. You must be 18 years or older to use this Service.</p>

<h2>3. Payment Terms</h2>
<p>Paid plans are billed monthly via Stripe. All plans include a 14-day free trial. You may cancel at any time through the Stripe customer portal. Refunds are handled on a case-by-case basis.</p>

<h2>4. Acceptable Use</h2>
<p>You agree not to misuse the Service. This includes attempting to access repositories you don't own, reverse-engineering the Service, or using it for any unlawful purpose.</p>

<h2>5. Data & Repository Access</h2>
<p>Tome accesses your repositories through GitHub's API using the permissions you grant. We read code diffs, documentation files, and file trees. We do not store your source code beyond what is needed for diff analysis (typically cached for less than 60 seconds).</p>

<h2>6. Service Availability</h2>
<p>We aim for high availability but do not guarantee uptime. The Service is provided "as is" without warranties of any kind.</p>

<h2>7. Limitation of Liability</h2>
<p>Tome HQ shall not be liable for any indirect, incidental, or consequential damages arising from your use of the Service. Our total liability is limited to the amount you paid for the Service in the 12 months preceding the claim.</p>

<h2>8. Changes to Terms</h2>
<p>We may update these terms. Continued use after changes constitutes acceptance. We will notify users of material changes via email.</p>

<h2>9. Contact</h2>
<p>Questions? Email <a href="mailto:support@tomehq.net" style="color: #6366f1;">support@tomehq.net</a></p>
"""))


@app.get("/privacy", response_class=HTMLResponse)
async def privacy():
    return HTMLResponse(_legal_page("Privacy Policy", """
<p><strong>Last updated:</strong> February 20, 2026</p>
<p>This Privacy Policy describes how Tome HQ ("we") collects, uses, and protects your information when you use Tome ("the Service").</p>

<h2>1. Information We Collect</h2>
<ul>
<li><strong>Account information:</strong> Email address, GitHub username</li>
<li><strong>Payment information:</strong> Processed by Stripe. We do not store credit card numbers.</li>
<li><strong>Repository data:</strong> Code diffs, file trees, and documentation content accessed via GitHub API during analysis. This data is processed transiently and not stored long-term.</li>
<li><strong>Usage data:</strong> API requests, scan results, documentation gaps detected</li>
</ul>

<h2>2. How We Use Your Information</h2>
<ul>
<li>To provide and improve the Service</li>
<li>To process payments</li>
<li>To communicate about your account and service updates</li>
<li>To detect and prevent abuse</li>
</ul>

<h2>3. Data Sharing</h2>
<p>We do not sell your data. We share data only with:</p>
<ul>
<li><strong>Stripe</strong> for payment processing</li>
<li><strong>GitHub</strong> for repository access (using your granted permissions)</li>
<li><strong>LLM providers</strong> (xAI/Anthropic) for diff analysis — code snippets are sent for analysis but not stored by us beyond the request</li>
</ul>

<h2>4. Data Retention</h2>
<p>Account data is retained while your account is active. Code diffs are processed transiently. Activity logs and gap reports are retained for the lifetime of your project. You may request deletion by contacting us.</p>

<h2>5. Security</h2>
<p>We use HTTPS encryption, secure API key storage, and follow security best practices. Repository access tokens are stored encrypted.</p>

<h2>6. Your Rights</h2>
<p>You may request access to, correction of, or deletion of your personal data at any time by emailing <a href="mailto:support@tomehq.net" style="color: #6366f1;">support@tomehq.net</a>.</p>

<h2>7. Changes</h2>
<p>We may update this policy. We will notify users of material changes via email.</p>

<h2>8. Contact</h2>
<p>Questions? Email <a href="mailto:support@tomehq.net" style="color: #6366f1;">support@tomehq.net</a></p>
"""))


def _legal_page(title: str, content: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Tome</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: #0a0a0b; color: #e4e4e7; line-height: 1.7; margin: 0;
  }}
  .container {{ max-width: 720px; margin: 0 auto; padding: 48px 24px; }}
  a.back {{ color: #6366f1; text-decoration: none; font-size: 14px; }}
  h1 {{ font-size: 32px; font-weight: 800; letter-spacing: -1px; margin: 24px 0; }}
  h2 {{ font-size: 18px; font-weight: 600; margin: 32px 0 8px; color: #e4e4e7; }}
  p, li {{ color: #a1a1aa; font-size: 15px; }}
  ul {{ padding-left: 20px; }}
  li {{ margin: 4px 0; }}
</style>
</head>
<body>
<div class="container">
  <a href="/" class="back">← Back to Tome</a>
  <h1>{title}</h1>
  {content}
</div>
</body>
</html>"""


# --- Dashboard ---

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    projects = list_projects()
    stats = get_stats()

    project_rows = ""
    for p in projects:
        project_rows += f"""
        <tr>
          <td><a href="/api/projects/{p['id']}" style="color: #6366f1; text-decoration: none;">{p['name']}</a></td>
          <td style="color: #71717a;">{p['github_owner']}/{p['github_repo']}</td>
          <td><span style="color: #22c55e;">{p['status']}</span></td>
        </tr>"""

    if not projects:
        project_rows = '<tr><td colspan="3" style="color: #71717a; text-align: center; padding: 32px;">No projects yet. <a href="/welcome" style="color: #6366f1;">Connect a repo →</a></td></tr>'

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard — Tome</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: #0a0a0b; color: #e4e4e7; margin: 0;
  }}
  .container {{ max-width: 960px; margin: 0 auto; padding: 32px 24px; }}
  nav {{
    border-bottom: 1px solid #1e1e22; padding: 16px 0;
    background: #0a0a0b;
  }}
  nav .container {{
    display: flex; justify-content: space-between; align-items: center;
  }}
  .logo {{
    font-size: 20px; font-weight: 700; letter-spacing: -0.5px;
    color: #e4e4e7; text-decoration: none;
  }}
  .logo span {{ color: #6366f1; }}
  .stats {{
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 16px; margin: 32px 0;
  }}
  .stat {{
    background: #141416; border: 1px solid #1e1e22; border-radius: 12px;
    padding: 24px;
  }}
  .stat-value {{
    font-size: 36px; font-weight: 800; letter-spacing: -1px;
  }}
  .stat-label {{ font-size: 13px; color: #71717a; margin-top: 4px; }}
  h2 {{
    font-size: 20px; font-weight: 700; margin: 32px 0 16px;
  }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 14px;
    background: #141416; border: 1px solid #1e1e22; border-radius: 12px;
    overflow: hidden;
  }}
  th {{
    text-align: left; padding: 12px 16px; color: #71717a;
    font-weight: 500; border-bottom: 1px solid #1e1e22;
  }}
  td {{
    padding: 12px 16px; border-bottom: 1px solid #1e1e22;
  }}
  .api-box {{
    background: #141416; border: 1px solid #1e1e22; border-radius: 12px;
    padding: 20px; margin-top: 24px;
    font-family: 'SF Mono', 'Cascadia Code', monospace; font-size: 13px;
    color: #a1a1aa;
  }}
  .api-box code {{ color: #6366f1; }}
</style>
</head>
<body>
<nav>
  <div class="container">
    <a href="/" class="logo">tome<span>.</span></a>
    <div style="display: flex; gap: 16px; align-items: center;">
      <a href="/welcome" style="color: #6366f1; text-decoration: none; font-size: 14px;">+ Add Repo</a>
      <span style="color: #1e1e22;">|</span>
      <span style="color: #71717a; font-size: 14px;">Dashboard</span>
    </div>
  </div>
</nav>
<div class="container">
  <div class="stats">
    <div class="stat">
      <div class="stat-value">{stats.get('total_projects', 0)}</div>
      <div class="stat-label">Projects</div>
    </div>
    <div class="stat">
      <div class="stat-value">{stats.get('total_gaps', 0)}</div>
      <div class="stat-label">Gaps Detected</div>
    </div>
    <div class="stat">
      <div class="stat-value">{stats.get('total_prs', 0)}</div>
      <div class="stat-label">PRs Opened</div>
    </div>
  </div>

  <h2>Projects</h2>
  <table>
    <tr><th>Name</th><th>Repository</th><th>Status</th></tr>
    {project_rows}
  </table>

  <div class="api-box">
    <strong style="color: #e4e4e7;">API Access</strong><br><br>
    Trigger a manual scan:<br>
    <code>curl -X POST {Config.BASE_URL}/api/projects/PROJECT_ID/scan</code><br><br>
    View documentation gaps:<br>
    <code>curl {Config.BASE_URL}/api/projects/PROJECT_ID/gaps</code><br><br>
    <a href="{Config.BASE_URL}/api/health" style="color: #6366f1; text-decoration: none; font-size: 12px;">API Health →</a>
  </div>
</div>
</body>
</html>""")


# --- Health & Stats ---

@app.get("/api/health")
async def health():
    llm_status = "unknown"
    model = ""

    if Config.LLM_BACKEND == "anthropic":
        llm_status = "configured" if Config.ANTHROPIC_API_KEY else "missing_key"
        model = Config.ANTHROPIC_MODEL
    elif Config.LLM_BACKEND == "xai":
        llm_status = "configured" if Config.XAI_API_KEY else "missing_key"
        model = Config.XAI_MODEL
    else:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{Config.OLLAMA_URL}/api/tags")
                llm_status = "connected" if r.status_code == 200 else "error"
        except Exception:
            llm_status = "disconnected"
        model = Config.OLLAMA_MODEL

    return {
        "status": "ok",
        "llm_backend": Config.LLM_BACKEND,
        "llm_status": llm_status,
        "model": model,
    }


@app.get("/api/stats")
async def stats():
    return get_stats()


# --- Project Management ---

@app.post("/api/projects")
async def create_project_route(request: Request):
    body = await request.json()
    required = ["name", "github_owner", "github_repo"]
    for field in required:
        if field not in body:
            raise HTTPException(400, f"Missing required field: {field}")

    result = create_project(
        name=body["name"],
        owner=body["github_owner"],
        repo=body["github_repo"],
        docs_paths=body.get("docs_paths", "docs/"),
        source_paths=body.get("source_paths", "src/"),
        default_branch=body.get("default_branch", "main"),
    )

    log_activity(result["id"], "project_created",
                 f"Project '{body['name']}' created for {body['github_owner']}/{body['github_repo']}")

    log.info("Project created: %s (%s/%s)", result["id"], body["github_owner"], body["github_repo"])
    return result


@app.get("/api/projects")
async def list_projects_route():
    return list_projects()


@app.get("/api/projects/{project_id}")
async def get_project_route(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@app.get("/api/projects/{project_id}/activity")
async def get_activity_route(project_id: str, limit: int = 50):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return get_activity(project_id, limit)


@app.get("/api/projects/{project_id}/gaps")
async def get_gaps_route(project_id: str, status: str = None):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return get_gaps(project_id, status)


# --- Repo Scan ---

@app.post("/api/projects/{project_id}/scan")
async def scan_route(project_id: str, background_tasks: BackgroundTasks):
    p = get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")

    background_tasks.add_task(engine.scan_repo, project_id)
    return {"status": "scan_started", "project_id": project_id}


# --- GitHub Webhook ---

@app.post("/api/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    event = request.headers.get("X-GitHub-Event", "")
    signature = request.headers.get("X-Hub-Signature-256", "")

    # Verify signature if secret is configured
    if Config.GITHUB_WEBHOOK_SECRET:
        if not _verify_signature(body, signature):
            raise HTTPException(401, "Invalid signature")

    payload = json.loads(body)

    if event == "ping":
        return {"status": "pong"}

    if event == "push":
        return await _handle_push(payload, background_tasks)

    if event == "pull_request":
        action = payload.get("action", "")
        if action == "closed" and payload.get("pull_request", {}).get("merged"):
            return await _handle_merged_pr(payload, background_tasks)

    return {"status": "ignored", "event": event}


async def _handle_push(payload: dict, background_tasks: BackgroundTasks):
    """Handle a push event."""
    repo_full = payload.get("repository", {}).get("full_name", "")
    before = payload.get("before", "")
    after = payload.get("after", "")
    ref = payload.get("ref", "")

    if not repo_full or not before or not after:
        return {"status": "ignored", "reason": "missing fields"}

    owner, repo = repo_full.split("/", 1)

    # Find matching project
    from db import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT id, default_branch FROM projects WHERE github_owner = ? AND github_repo = ? AND status = 'active'",
        (owner, repo)
    ).fetchone()
    conn.close()

    if not row:
        return {"status": "ignored", "reason": "no matching project"}

    # Only process pushes to default branch
    expected_ref = f"refs/heads/{row['default_branch']}"
    if ref != expected_ref:
        return {"status": "ignored", "reason": f"push to {ref}, not {expected_ref}"}

    # Skip if this is an all-zeros "before" (new branch)
    if before == "0" * 40:
        return {"status": "ignored", "reason": "branch creation, no diff"}

    log.info("Processing push to %s: %s..%s", repo_full, before[:7], after[:7])
    background_tasks.add_task(engine.process_push, row["id"], before, after)

    return {"status": "processing", "project_id": row["id"]}


async def _handle_merged_pr(payload: dict, background_tasks: BackgroundTasks):
    """Handle a merged PR — same as push, analyze the merge commit."""
    pr = payload.get("pull_request", {})
    repo_full = payload.get("repository", {}).get("full_name", "")

    # Skip PRs created by Tome itself
    head_ref = pr.get("head", {}).get("ref", "")
    if head_ref.startswith(Config.TOME_BRANCH_PREFIX):
        return {"status": "ignored", "reason": "tome's own PR"}

    owner, repo = repo_full.split("/", 1)
    base_sha = pr.get("base", {}).get("sha", "")
    merge_sha = pr.get("merge_commit_sha", "")

    if not base_sha or not merge_sha:
        return {"status": "ignored", "reason": "missing SHAs"}

    from db import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM projects WHERE github_owner = ? AND github_repo = ? AND status = 'active'",
        (owner, repo)
    ).fetchone()
    conn.close()

    if not row:
        return {"status": "ignored", "reason": "no matching project"}

    log.info("Processing merged PR #%s on %s", pr.get("number"), repo_full)
    background_tasks.add_task(engine.process_push, row["id"], base_sha, merge_sha)

    return {"status": "processing", "project_id": row["id"]}


def _verify_signature(payload: bytes, signature: str) -> bool:
    if not signature:
        return False
    expected = "sha256=" + hmac.new(
        Config.GITHUB_WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# --- Stripe Billing ---

@app.post("/api/checkout")
async def checkout(request: Request):
    body = await request.json()
    plan = body.get("plan", "pro")
    email = body.get("email")

    try:
        session = await billing.create_checkout_session(plan, email)
        return {"checkout_url": session.get("url", "")}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        log.error("Stripe checkout error: %s", e)
        raise HTTPException(500, "Failed to create checkout session")


@app.post("/api/onboard")
async def onboard(request: Request, background_tasks: BackgroundTasks):
    """Full onboarding: verify repo access, create project, set up webhook, run initial scan."""
    body = await request.json()

    required = ["email", "github_owner", "github_repo", "github_token"]
    for field in required:
        if not body.get(field):
            raise HTTPException(400, f"Missing required field: {field}")

    owner = body["github_owner"].strip()
    repo = body["github_repo"].strip()
    token = body["github_token"].strip()
    email = body["email"].strip()

    # 1. Verify repo access
    try:
        repo_info = await gh.verify_repo_access(owner, repo, token)
    except Exception as e:
        log.warning("Repo access failed for %s/%s: %s", owner, repo, e)
        raise HTTPException(400, f"Cannot access {owner}/{repo}. Check your token has 'repo' scope.")

    # 2. Create or find customer
    customer = get_customer_by_email(email)
    if not customer:
        customer = create_customer(email=email)

    # 3. Store their GitHub token
    update_customer_github_token(customer["id"], token)

    # 4. Create the project
    default_branch = body.get("default_branch", repo_info.get("default_branch", "main"))
    result = create_project(
        name=repo_info.get("full_name", f"{owner}/{repo}"),
        owner=owner,
        repo=repo,
        docs_paths=body.get("docs_paths", "docs/"),
        source_paths=body.get("source_paths", "src/"),
        default_branch=default_branch,
    )

    # 5. Link project to customer
    link_project_to_customer(result["id"], customer["id"])

    # 6. Set up webhook on the repo
    webhook_ok = False
    try:
        await gh.create_webhook(owner, repo, token)
        webhook_ok = True
    except Exception as e:
        log.warning("Webhook creation failed for %s/%s: %s (may already exist)", owner, repo, e)
        # Not fatal — they may have already set it up, or can do it manually

    log_activity(result["id"], "project_onboarded",
                 f"Project onboarded by {email}. Webhook: {'OK' if webhook_ok else 'manual setup needed'}")

    # 7. Kick off initial scan in background
    background_tasks.add_task(engine.scan_repo, result["id"])

    log.info("Onboarded: %s/%s for %s (project=%s)", owner, repo, email, result["id"])
    return {
        "project_id": result["id"],
        "api_key": result["api_key"],
        "webhook": "configured" if webhook_ok else "manual_setup_needed",
        "scan": "started",
    }


@app.post("/api/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")

    if not billing.verify_webhook_signature(body, sig):
        raise HTTPException(401, "Invalid signature")

    try:
        event = json.loads(body)
        await billing.handle_webhook_event(event)
        return {"status": "ok"}
    except Exception as e:
        log.error("Stripe webhook error: %s", e)
        raise HTTPException(500, "Webhook processing failed")


@app.get("/welcome", response_class=HTMLResponse)
async def welcome(session_id: str = None):
    # Try to look up customer email from Stripe session
    email = ""
    if session_id:
        try:
            session = await billing.get_session(session_id)
            email = session.get("customer_email", "") or session.get("customer_details", {}).get("email", "")
        except Exception:
            pass

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Welcome to Tome — Connect Your Repo</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: #0a0a0b; color: #e4e4e7; margin: 0;
    display: flex; align-items: center; justify-content: center; min-height: 100vh;
  }}
  .card {{
    background: #141416; border: 1px solid #1e1e22; border-radius: 16px;
    padding: 48px; max-width: 560px; width: 100%;
  }}
  h1 {{ font-size: 28px; font-weight: 800; letter-spacing: -1px; margin-bottom: 8px; }}
  h1 span {{ color: #6366f1; }}
  .subtitle {{ color: #71717a; font-size: 15px; margin-bottom: 32px; }}
  .step-indicator {{
    display: flex; gap: 8px; margin-bottom: 24px;
  }}
  .step-dot {{
    width: 8px; height: 8px; border-radius: 50%; background: #1e1e22;
  }}
  .step-dot.active {{ background: #6366f1; }}
  label {{
    display: block; font-size: 13px; font-weight: 600; color: #a1a1aa;
    margin-bottom: 6px; margin-top: 16px;
  }}
  input, select {{
    width: 100%; padding: 10px 12px; border-radius: 8px;
    border: 1px solid #1e1e22; background: #0a0a0b; color: #e4e4e7;
    font-size: 14px; font-family: inherit; box-sizing: border-box;
  }}
  input:focus, select:focus {{
    outline: none; border-color: #6366f1;
  }}
  input::placeholder {{ color: #52525b; }}
  .help {{ font-size: 12px; color: #52525b; margin-top: 4px; }}
  .help a {{ color: #6366f1; text-decoration: none; }}
  button {{
    width: 100%; padding: 14px; border-radius: 8px; border: none;
    background: #6366f1; color: white; font-size: 16px; font-weight: 600;
    cursor: pointer; margin-top: 24px; transition: background 0.15s;
    font-family: inherit;
  }}
  button:hover {{ background: #4f46e5; }}
  button:disabled {{ background: #27272a; color: #52525b; cursor: not-allowed; }}
  .error {{ color: #ef4444; font-size: 13px; margin-top: 8px; display: none; }}
  .success {{ display: none; text-align: center; }}
  .success h2 {{ font-size: 24px; font-weight: 700; margin-bottom: 12px; }}
  .success p {{ color: #71717a; font-size: 15px; margin-bottom: 24px; }}
  .success a {{
    display: inline-block; background: #6366f1; color: white;
    padding: 12px 28px; border-radius: 8px; text-decoration: none;
    font-weight: 600;
  }}
  .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
</style>
</head>
<body>
<div class="card">
  <div id="form-view">
    <h1>Welcome to <span>Tome</span></h1>
    <p class="subtitle">Connect your repository to start autonomous doc maintenance.</p>
    <div class="step-indicator">
      <div class="step-dot active"></div>
      <div class="step-dot"></div>
      <div class="step-dot"></div>
    </div>

    <form id="onboard-form" onsubmit="return submitOnboarding(event)">
      <label>Email</label>
      <input type="email" name="email" placeholder="you@company.com" value="{email}" required>

      <label>GitHub Repository</label>
      <div class="row">
        <input type="text" name="github_owner" placeholder="owner / org" required>
        <input type="text" name="github_repo" placeholder="repository" required>
      </div>

      <label>GitHub Personal Access Token</label>
      <input type="password" name="github_token" placeholder="ghp_..." required>
      <p class="help">Needs <code>repo</code> scope. <a href="https://github.com/settings/tokens/new?scopes=repo&description=Tome" target="_blank">Create one here →</a></p>

      <div class="row">
        <div>
          <label>Docs Path</label>
          <input type="text" name="docs_paths" value="docs/" placeholder="docs/">
        </div>
        <div>
          <label>Source Path</label>
          <input type="text" name="source_paths" value="src/" placeholder="src/">
        </div>
      </div>

      <label>Default Branch</label>
      <input type="text" name="default_branch" value="main" placeholder="main">

      <div class="error" id="error-msg"></div>
      <button type="submit" id="submit-btn">Connect Repository</button>
    </form>
  </div>

  <div class="success" id="success-view">
    <h2>You're all set!</h2>
    <p>Tome is now watching your repo. Push code and we'll open PRs when docs need updating.</p>
    <p style="color: #52525b; font-size: 13px; margin-bottom: 16px;" id="project-info"></p>
    <a href="/dashboard">Go to Dashboard</a>
  </div>
</div>

<script>
async function submitOnboarding(e) {{
  e.preventDefault();
  const form = e.target;
  const btn = document.getElementById('submit-btn');
  const errEl = document.getElementById('error-msg');
  errEl.style.display = 'none';
  btn.disabled = true;
  btn.textContent = 'Connecting...';

  const data = {{
    email: form.email.value,
    github_owner: form.github_owner.value,
    github_repo: form.github_repo.value,
    github_token: form.github_token.value,
    docs_paths: form.docs_paths.value,
    source_paths: form.source_paths.value,
    default_branch: form.default_branch.value,
  }};

  try {{
    const resp = await fetch('/api/onboard', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(data)
    }});
    const result = await resp.json();
    if (!resp.ok) {{
      throw new Error(result.detail || 'Setup failed');
    }}
    document.getElementById('form-view').style.display = 'none';
    document.getElementById('success-view').style.display = 'block';
    document.getElementById('project-info').textContent =
      'Project ID: ' + result.project_id + ' | API Key: ' + result.api_key;
  }} catch (err) {{
    errEl.textContent = err.message;
    errEl.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Connect Repository';
  }}
}}
</script>
</body>
</html>""")
