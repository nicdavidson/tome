# Tome

**Documentation that maintains itself.** Tome watches your codebase for changes and opens PRs to keep your docs current.

[tomehq.net](https://tomehq.net) | $9/mo Starter | $29/mo Pro | $99/mo Enterprise | 14-day free trial

## How it works

1. **Connect** — point Tome at your repo and docs directory (30 seconds)
2. **Push code** — every push is analyzed for documentation impact
3. **Review a PR** — Tome detects gaps, writes updates in your style, and opens a PR

No new tools to learn. No workflow changes. Doc updates arrive as PRs your team already knows how to review.

## Why not just build this yourself?

You could wire up a webhook and an LLM call in a day. The hard part is everything else:

- **Style matching** across your existing docs
- **Multi-file change handling** that spans documentation
- **Signal vs noise** — not generating garbage PRs your team ignores
- **Scaling** across repos and contributors
- **Keeping it running** while you ship product

That's the problem space Tome lives in.

## Self-hosted quick start

```bash
git clone https://github.com/nicdavidson/tome.git
cd tome

cp .env.example .env
# Edit .env with your GitHub token and LLM API key

pip install -r requirements.txt
python run.py
```

Runs on port 8400 by default. Visit `http://localhost:8400`.

## LLM backends

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
| `POST` | `/api/checkout` | Create Stripe checkout session |
| `POST` | `/api/onboard` | Onboard new repo (verify, webhook, scan) |

## Architecture

```
GitHub Push → Webhook → Diff Analyzer → Gap Detector → Doc Generator → PR Creator
                              ↓                              ↓
                         LLM (Grok/Claude/Ollama)      GitHub API
```

Per-customer GitHub tokens. Multi-tenant. All state in SQLite (WAL mode). Deployed on Fly.io.

## License

MIT
