# Tome

**Autonomous documentation maintenance.** Tome watches your codebase for changes and opens PRs to keep your docs current.

Not a chatbot. A docs engineer.

## What it does

1. **Watches** — monitors every push to your repo's default branch
2. **Analyzes** — LLM-powered diff analysis identifies doc-relevant code changes
3. **Detects gaps** — compares changes against existing docs to find what's missing
4. **Opens PRs** — generates documentation and opens pull requests in your style

## Quick Start

```bash
# Clone
git clone https://github.com/nicdavidson/tome.git
cd tome

# Configure
cp .env.example .env
# Edit .env with your GitHub token and LLM API key

# Run
pip install -r requirements.txt
python run.py
```

Tome runs on port 8400 by default. Visit `http://localhost:8400` for the landing page.

## Create a project

```bash
curl -X POST http://localhost:8400/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Project",
    "github_owner": "yourorg",
    "github_repo": "yourrepo",
    "docs_paths": "docs/",
    "source_paths": "src/",
    "default_branch": "main"
  }'
```

## Trigger a scan

```bash
curl -X POST http://localhost:8400/api/projects/{id}/scan
```

## LLM Backends

Tome supports three LLM backends. Set via environment variable or auto-detected from API keys:

| Backend | Model | Best for |
|---------|-------|----------|
| **xAI (Grok)** | `grok-3-mini-fast` | Cost-efficient production use |
| **Anthropic** | `claude-haiku-4-5-20251001` | High-quality output |
| **Ollama** | `llama3.2:3b` | Local development, no API costs |

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check + LLM status |
| `GET` | `/api/stats` | Overall statistics |
| `POST` | `/api/projects` | Create a project |
| `GET` | `/api/projects` | List all projects |
| `GET` | `/api/projects/{id}` | Project details |
| `GET` | `/api/projects/{id}/activity` | Activity log |
| `GET` | `/api/projects/{id}/gaps` | Documentation gaps |
| `POST` | `/api/projects/{id}/scan` | Full repo scan |
| `POST` | `/api/webhook/github` | GitHub webhook receiver |

## Deploy to Fly.io

```bash
fly launch
fly secrets set TOME_GITHUB_TOKEN=ghp_xxx XAI_API_KEY=xai-xxx
fly deploy
```

## Architecture

```
GitHub Push → Webhook → Diff Analyzer → Gap Detector → Doc Generator → PR Creator
                              ↓                              ↓
                         LLM (Grok/Claude/Ollama)      GitHub API
```

All state stored in SQLite. No external database required.

## License

MIT
