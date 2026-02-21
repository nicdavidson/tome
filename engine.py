"""Tome Engine — the brain.

Pipeline:
1. Receive a push event or manual scan trigger
2. Get the diff or full repo state
3. Analyze for doc-relevant changes
4. Check existing docs for coverage gaps
5. Generate doc content for each gap
6. Open a PR with all doc updates
"""
import re
import json
import logging
from datetime import datetime
import httpx
from config import Config
import github_client as gh
import db

log = logging.getLogger("tome.engine")


async def llm_generate(prompt: str, json_mode: bool = False) -> str:
    """Call configured LLM backend (Anthropic, xAI, or Ollama)."""
    if Config.LLM_BACKEND == "anthropic":
        return await _anthropic_generate(prompt, json_mode)
    if Config.LLM_BACKEND == "xai":
        return await _xai_generate(prompt, json_mode)
    return await _ollama_generate(prompt, json_mode)


async def _anthropic_generate(prompt: str, json_mode: bool = False) -> str:
    """Call Anthropic Claude API."""
    messages = [{"role": "user", "content": prompt}]
    payload = {
        "model": Config.ANTHROPIC_MODEL,
        "max_tokens": 4096,
        "messages": messages,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": Config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload
        )
        resp.raise_for_status()
        data = resp.json()
        text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        return "\n".join(text_blocks)


async def _xai_generate(prompt: str, json_mode: bool = False) -> str:
    """Call xAI Grok API (OpenAI-compatible)."""
    messages = [{"role": "user", "content": prompt}]
    payload = {
        "model": Config.XAI_MODEL,
        "max_tokens": 4096,
        "messages": messages,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {Config.XAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _ollama_generate(prompt: str, json_mode: bool = False) -> str:
    """Call local Ollama instance."""
    payload = {
        "model": Config.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if json_mode:
        payload["format"] = "json"

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{Config.OLLAMA_URL}/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json().get("response", "")


async def analyze_diff(diff_text: str) -> list[dict]:
    """Analyze a git diff and identify doc-relevant changes."""
    truncated = diff_text[:Config.MAX_DIFF_SIZE]

    prompt = f"""You are a documentation analyst. Analyze this git diff and identify changes that need documentation updates.

For each doc-relevant change, output a JSON object with:
- "file": source file that changed
- "change_type": one of "new_function", "changed_api", "new_endpoint", "new_feature", "breaking_change", "config_change", "new_module"
- "summary": one-line description
- "details": what specifically should be documented

Rules:
- Only include changes users/developers need to know about
- Skip: variable renames, formatting, internal refactors, test-only changes, dependency bumps
- Be specific about what changed

Return a JSON object with key "changes" containing an array. If nothing is doc-relevant, return {{"changes": []}}.

Diff:
```
{truncated}
```"""

    text = await llm_generate(prompt, json_mode=True)

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data.get("changes", [])
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        log.warning("Failed to parse LLM response as JSON: %s", text[:200])
        return []


async def find_doc_gaps(changes: list[dict], doc_files: dict[str, str]) -> list[dict]:
    """Check which changes lack documentation coverage."""
    if not changes:
        return []

    all_docs_lower = "\n".join(doc_files.values()).lower()
    gaps = []

    for change in changes:
        summary = change.get("summary", "")
        details = change.get("details", "")
        search_text = f"{summary} {details}".lower()

        # Extract meaningful terms
        terms = _extract_terms(search_text)
        if not terms:
            continue

        # Check how many terms appear in existing docs
        hits = sum(1 for t in terms if t in all_docs_lower)
        coverage = hits / len(terms)

        if coverage < 0.4:
            change["doc_coverage"] = round(coverage, 2)
            gaps.append(change)

    return gaps


def _extract_terms(text: str) -> list[str]:
    """Extract key terms for doc coverage matching."""
    stop = {
        'the', 'a', 'an', 'in', 'to', 'for', 'of', 'and', 'or', 'is', 'was',
        'with', 'that', 'this', 'add', 'added', 'new', 'update', 'change',
        'changed', 'remove', 'removed', 'function', 'method', 'class', 'file',
        'now', 'can', 'has', 'have', 'been', 'from', 'will', 'are', 'not',
    }
    words = re.findall(r'[a-z_][a-z0-9_]{2,}', text.lower())
    return [w for w in words if w not in stop]


async def generate_doc_update(gap: dict, doc_files: dict[str, str],
                               diff_context: str) -> dict:
    """Generate documentation content for a single gap.

    Returns: {filename, content, is_new, gap}
    """
    source_file = gap.get("file", "unknown")
    base_name = source_file.rsplit("/", 1)[-1].rsplit(".", 1)[0]

    # Find existing doc file for this module
    target_doc = None
    for doc_path in doc_files:
        doc_basename = doc_path.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        if base_name.lower() == doc_basename or base_name.lower() in doc_basename:
            target_doc = doc_path
            break

    if target_doc and target_doc in doc_files:
        existing = doc_files[target_doc][:Config.MAX_DOC_CONTEXT]
        prompt = f"""Update this documentation to cover the following change.

Existing doc ({target_doc}):
```markdown
{existing}
```

Change to document:
- Source file: {gap['file']}
- Type: {gap.get('change_type', 'unknown')}
- Summary: {gap.get('summary', '')}
- Details: {gap.get('details', '')}

Diff context:
```
{diff_context[:2000]}
```

Write the COMPLETE updated document. Keep existing content, add coverage for the new change.
Match the existing style and structure exactly. Output only the markdown."""
        is_new = False
    else:
        target_doc = f"docs/{base_name}.md"
        style_hint = ""
        if doc_files:
            sample = list(doc_files.values())[0][:800]
            style_hint = f"\nMatch this documentation style:\n```\n{sample}\n```\n"

        prompt = f"""Write documentation for the following code change.
{style_hint}
Change:
- Source file: {gap['file']}
- Type: {gap.get('change_type', 'unknown')}
- Summary: {gap.get('summary', '')}
- Details: {gap.get('details', '')}

Code context:
```
{diff_context[:3000]}
```

Write clear, useful markdown documentation. Include:
- What this does and why it matters
- How to use it with code examples
- Parameters/options if applicable
- Common patterns or gotchas

Output only markdown."""
        is_new = True

    content = await llm_generate(prompt)

    return {
        "filename": target_doc,
        "content": content.strip(),
        "is_new": is_new,
        "gap": gap,
    }


async def process_push(project_id: str, before: str, after: str):
    """Full pipeline: push event → analysis → doc PRs."""
    project = db.get_project(project_id)
    if not project:
        log.error("Project %s not found", project_id)
        return

    owner = project["github_owner"]
    repo = project["github_repo"]
    docs_path = project["docs_paths"]
    default_branch = project["default_branch"]

    # Look up per-customer GitHub token
    token = db.get_project_github_token(project_id)

    db.log_activity(project_id, "push_received",
                    f"Push received: {before[:7]}..{after[:7]}")

    # 1. Get the diff
    try:
        diff_text = await gh.get_push_diff(owner, repo, before, after, token=token)
    except Exception as e:
        log.error("Failed to get diff: %s", e)
        db.log_activity(project_id, "error", f"Failed to get diff: {e}")
        return

    if not diff_text.strip():
        db.log_activity(project_id, "no_changes", "Push had no meaningful diff")
        return

    # 2. Analyze for doc-relevant changes
    changes = await analyze_diff(diff_text)
    if not changes:
        db.log_activity(project_id, "no_doc_changes",
                        "No documentation-relevant changes detected")
        return

    db.log_activity(project_id, "changes_detected",
                    f"Found {len(changes)} doc-relevant changes",
                    json.dumps(changes, indent=2))

    # 3. Get existing docs
    doc_files = await gh.get_all_doc_files(owner, repo, docs_path, token=token)

    # 4. Find gaps
    gaps = await find_doc_gaps(changes, doc_files)
    if not gaps:
        db.log_activity(project_id, "no_gaps",
                        f"All {len(changes)} changes are already documented")
        return

    db.log_activity(project_id, "gaps_found",
                    f"Found {len(gaps)} documentation gaps",
                    json.dumps(gaps, indent=2))

    # 5. Generate docs for each gap
    doc_updates = []
    for gap in gaps:
        gap_id = db.create_gap(
            project_id, gap.get("file", "unknown"),
            gap.get("change_type", "unknown"),
            gap.get("summary", "")
        )
        gap["_db_id"] = gap_id

        try:
            update = await generate_doc_update(gap, doc_files, diff_text)
            if update["content"]:
                doc_updates.append(update)
        except Exception as e:
            log.error("Failed to generate doc for gap %s: %s", gap_id, e)

    if not doc_updates:
        db.log_activity(project_id, "generation_failed", "Doc generation produced no content")
        return

    # 6. Create branch, commit docs, open PR
    try:
        result = await _create_doc_pr(owner, repo, default_branch, doc_updates, project_id, token=token)
        db.log_activity(project_id, "pr_opened",
                        f"PR #{result['number']}: {result['title']}",
                        result["url"])

        for update in doc_updates:
            gap = update["gap"]
            if "_db_id" in gap:
                db.update_gap(gap["_db_id"], "pr_opened",
                              pr_number=result["number"], pr_url=result["url"],
                              doc_file=update["filename"])

    except Exception as e:
        log.error("Failed to create PR: %s", e)
        db.log_activity(project_id, "pr_failed", f"Failed to create PR: {e}")


async def scan_repo(project_id: str):
    """Full repo scan — find all doc gaps, not just from a push."""
    project = db.get_project(project_id)
    if not project:
        return {"error": "Project not found"}

    owner = project["github_owner"]
    repo = project["github_repo"]
    docs_path = project["docs_paths"]
    source_paths = project["source_paths"].split(",")

    # Look up per-customer GitHub token
    token = db.get_project_github_token(project_id)

    db.log_activity(project_id, "scan_started", "Full repository scan initiated")

    # Get all doc files
    doc_files = await gh.get_all_doc_files(owner, repo, docs_path, token=token)

    # Get full file tree
    tree = await gh.get_tree(owner, repo, project["default_branch"], token=token)
    source_files = [
        f for f in tree
        if f["type"] == "blob"
        and any(f["path"].startswith(sp.strip()) for sp in source_paths)
        and f["path"].endswith((".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".php"))
    ]

    # Check each source file for doc coverage
    all_doc_text = "\n".join(doc_files.values()).lower()
    uncovered = []

    for sf in source_files:
        basename = sf["path"].rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        # Check if this module has any documentation
        has_doc = any(basename in dp.lower() for dp in doc_files)
        mentioned = basename in all_doc_text

        if not has_doc and not mentioned:
            uncovered.append(sf["path"])

    # Log results
    coverage_pct = round((1 - len(uncovered) / max(len(source_files), 1)) * 100, 1)
    db.log_activity(project_id, "scan_complete",
                    f"Scan complete: {coverage_pct}% coverage ({len(source_files)} source files, {len(uncovered)} undocumented)",
                    json.dumps({"uncovered": uncovered, "total_source": len(source_files),
                               "total_docs": len(doc_files), "coverage_pct": coverage_pct}))

    for path in uncovered:
        db.create_gap(project_id, path, "missing_doc",
                      f"Source file {path} has no corresponding documentation")

    return {
        "coverage_pct": coverage_pct,
        "total_source_files": len(source_files),
        "total_doc_files": len(doc_files),
        "undocumented_files": uncovered,
        "gaps_created": len(uncovered),
    }


async def _create_doc_pr(owner: str, repo: str, base_branch: str,
                          doc_updates: list[dict], project_id: str, token: str = None) -> dict:
    """Create a branch, commit all doc updates, open a PR."""
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    branch_name = f"{Config.TOME_BRANCH_PREFIX}docs-update-{timestamp}"

    # Get base branch SHA
    base_sha = await gh.get_default_branch_sha(owner, repo, base_branch, token=token)

    # Create branch
    created = await gh.create_branch(owner, repo, branch_name, base_sha, token=token)
    if not created:
        raise RuntimeError(f"Failed to create branch {branch_name}")

    # Commit each doc file
    files_changed = []
    for update in doc_updates:
        path = update["filename"]
        existing_sha = await gh.get_file_sha(owner, repo, path, branch_name, token=token)

        action = "Update" if existing_sha else "Add"
        msg = f"docs: {action.lower()} {path}\n\n{update['gap'].get('summary', 'Documentation update')}\n\nGenerated by Tome"

        await gh.create_or_update_file(
            owner, repo, path, update["content"], msg, branch_name, existing_sha, token=token
        )
        files_changed.append(f"- {'Updated' if existing_sha else 'Created'}: `{path}`")

    # Build PR body
    changes_summary = "\n".join(
        f"- **{u['gap'].get('change_type', 'change')}** in `{u['gap'].get('file', '?')}`: {u['gap'].get('summary', '')}"
        for u in doc_updates
    )
    files_list = "\n".join(files_changed)

    pr_body = f"""## Documentation Updates

Tome detected code changes that need documentation coverage.

### Changes Detected
{changes_summary}

### Files Modified
{files_list}

---
*Generated automatically by [Tome](https://tomehq.net) — your autonomous docs engineer.*
"""

    title = f"docs: update documentation ({len(doc_updates)} {'file' if len(doc_updates) == 1 else 'files'})"

    pr = await gh.create_pull_request(owner, repo, title, pr_body, branch_name, base_branch, token=token)

    return {
        "number": pr["number"],
        "title": title,
        "url": pr["html_url"],
    }
