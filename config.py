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

    # LLM backend: "anthropic" or "ollama"
    LLM_BACKEND = os.getenv("TOME_LLM_BACKEND", "anthropic" if os.getenv("ANTHROPIC_API_KEY") else "ollama")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("TOME_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    OLLAMA_URL = os.getenv("TOME_OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("TOME_OLLAMA_MODEL", "llama3.2:3b")
