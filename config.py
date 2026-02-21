import os

class Config:
    DB_PATH = os.getenv("TOME_DB", "/data/projects/tome/tome.db")
    GITHUB_TOKEN = os.getenv("TOME_GITHUB_TOKEN", "")
    GITHUB_WEBHOOK_SECRET = os.getenv("TOME_WEBHOOK_SECRET", "")
    HOST = os.getenv("TOME_HOST", "0.0.0.0")
    PORT = int(os.getenv("TOME_PORT", "8400"))
    STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    TOME_BRANCH_PREFIX = "tome/"
    MAX_DIFF_SIZE = 8000
    MAX_DOC_CONTEXT = 4000

    # LLM backend: "anthropic", "xai", or "ollama"
    # Auto-detects based on available API keys
    LLM_BACKEND = os.getenv("TOME_LLM_BACKEND",
        "anthropic" if os.getenv("ANTHROPIC_API_KEY")
        else "xai" if os.getenv("XAI_API_KEY")
        else "ollama"
    )
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("TOME_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    XAI_API_KEY = os.getenv("XAI_API_KEY", "")
    XAI_MODEL = os.getenv("TOME_XAI_MODEL", "grok-3-mini-fast")
    OLLAMA_URL = os.getenv("TOME_OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("TOME_OLLAMA_MODEL", "llama3.2:3b")

    # Stripe
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRICES = {
        "starter": os.getenv("STRIPE_PRICE_STARTER", "price_1T34JQEy0xJzw2UF59MTcJ8Z"),
        "pro": os.getenv("STRIPE_PRICE_PRO", "price_1T34JQEy0xJzw2UFNx8yV2EI"),
        "enterprise": os.getenv("STRIPE_PRICE_ENTERPRISE", "price_1T34JREy0xJzw2UFixi31mmj"),
    }
    BASE_URL = os.getenv("TOME_BASE_URL", "https://tomehq.net")
