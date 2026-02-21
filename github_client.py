"""GitHub API client for Tome.

Handles all GitHub interactions: reading repos, getting diffs,
creating branches, committing files, and opening PRs.
"""
import httpx
import base64
import hashlib
import hmac
from datetime import datetime
from config import Config

API = "https://api.github.com"


def _headers(token: str = None) -> dict:
    t = token or Config.GITHUB_TOKEN
    return {
        "Authorization": f"Bearer {t}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    if not Config.GITHUB_WEBHOOK_SECRET:
        return True  # no secret configured, skip verification (dev mode)
    expected = "sha256=" + hmac.new(
        Config.GITHUB_WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def get_repo_info(owner: str, repo: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{API}/repos/{owner}/{repo}", headers=_headers())
        resp.raise_for_status()
        return resp.json()


async def get_compare(owner: str, repo: str, base: str, head: str) -> dict:
    """Get diff between two commits."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API}/repos/{owner}/{repo}/compare/{base}...{head}",
            headers=_headers()
        )
        resp.raise_for_status()
        return resp.json()


async def get_commit_diff(owner: str, repo: str, sha: str) -> str:
    """Get the patch/diff for a specific commit."""
    headers = _headers()
    headers["Accept"] = "application/vnd.github.v3.diff"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API}/repos/{owner}/{repo}/commits/{sha}",
            headers=headers
        )
        resp.raise_for_status()
        return resp.text


async def get_push_diff(owner: str, repo: str, before: str, after: str) -> str:
    """Get combined diff for a push (multiple commits)."""
    headers = _headers()
    headers["Accept"] = "application/vnd.github.v3.diff"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API}/repos/{owner}/{repo}/compare/{before}...{after}",
            headers=headers
        )
        resp.raise_for_status()
        return resp.text


async def list_directory(owner: str, repo: str, path: str, ref: str = None) -> list[dict]:
    """List files in a repo directory."""
    params = {}
    if ref:
        params["ref"] = ref
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(),
            params=params
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else [data]


async def get_file_content(owner: str, repo: str, path: str, ref: str = None) -> str | None:
    """Get decoded content of a file."""
    params = {}
    if ref:
        params["ref"] = ref
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(),
            params=params
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return data.get("content", "")


async def get_all_doc_files(owner: str, repo: str, docs_path: str, ref: str = None) -> dict[str, str]:
    """Recursively get all markdown files in docs directory. Returns {path: content}."""
    result = {}
    await _walk_docs(owner, repo, docs_path.rstrip("/"), ref, result)
    return result


async def _walk_docs(owner: str, repo: str, path: str, ref: str, result: dict):
    items = await list_directory(owner, repo, path, ref)
    for item in items:
        if item["type"] == "dir":
            await _walk_docs(owner, repo, item["path"], ref, result)
        elif item["type"] == "file" and item["name"].endswith((".md", ".mdx", ".rst", ".txt")):
            content = await get_file_content(owner, repo, item["path"], ref)
            if content:
                result[item["path"]] = content


async def get_tree(owner: str, repo: str, ref: str = "HEAD") -> list[dict]:
    """Get full file tree of a repo (recursive)."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API}/repos/{owner}/{repo}/git/trees/{ref}?recursive=1",
            headers=_headers()
        )
        resp.raise_for_status()
        return resp.json().get("tree", [])


async def get_default_branch_sha(owner: str, repo: str, branch: str) -> str:
    """Get the latest commit SHA of a branch."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API}/repos/{owner}/{repo}/git/refs/heads/{branch}",
            headers=_headers()
        )
        resp.raise_for_status()
        return resp.json()["object"]["sha"]


async def create_branch(owner: str, repo: str, branch_name: str, from_sha: str) -> bool:
    """Create a new branch from a commit SHA."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{API}/repos/{owner}/{repo}/git/refs",
            headers=_headers(),
            json={"ref": f"refs/heads/{branch_name}", "sha": from_sha}
        )
        return resp.status_code == 201


async def create_or_update_file(owner: str, repo: str, path: str, content: str,
                                 message: str, branch: str, sha: str = None) -> dict:
    """Create or update a file in the repo."""
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.put(
            f"{API}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(),
            json=payload
        )
        resp.raise_for_status()
        return resp.json()


async def get_file_sha(owner: str, repo: str, path: str, branch: str) -> str | None:
    """Get the SHA of an existing file (needed for updates)."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(),
            params={"ref": branch}
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("sha")


async def create_pull_request(owner: str, repo: str, title: str, body: str,
                               head: str, base: str) -> dict:
    """Create a pull request."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{API}/repos/{owner}/{repo}/pulls",
            headers=_headers(),
            json={"title": title, "body": body, "head": head, "base": base}
        )
        resp.raise_for_status()
        return resp.json()


async def create_webhook(owner: str, repo: str, token: str = None) -> dict:
    """Create a webhook on the repo to receive push and PR events."""
    webhook_url = f"{Config.BASE_URL}/api/webhook/github"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{API}/repos/{owner}/{repo}/hooks",
            headers=_headers(token),
            json={
                "name": "web",
                "active": True,
                "events": ["push", "pull_request"],
                "config": {
                    "url": webhook_url,
                    "content_type": "json",
                    "secret": Config.GITHUB_WEBHOOK_SECRET or "",
                    "insecure_ssl": "0",
                },
            },
        )
        resp.raise_for_status()
        return resp.json()


async def verify_repo_access(owner: str, repo: str, token: str) -> dict:
    """Verify we can access the repo with the given token. Returns repo info or raises."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{API}/repos/{owner}/{repo}",
            headers=_headers(token),
        )
        resp.raise_for_status()
        return resp.json()
