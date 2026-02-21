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
from db import init_db, create_project, get_project, list_projects, log_activity
from db import get_activity, get_gaps, get_stats, verify_api_key
import engine
import github_client as gh

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


# --- Health & Stats ---

@app.get("/api/health")
async def health():
    llm_status = "unknown"
    model = ""

    if Config.LLM_BACKEND == "anthropic":
        llm_status = "configured" if Config.ANTHROPIC_API_KEY else "missing_key"
        model = Config.ANTHROPIC_MODEL
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
