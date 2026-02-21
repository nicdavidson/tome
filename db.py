import sqlite3
import uuid
import json
from datetime import datetime
from config import Config


def get_db():
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        github_owner TEXT NOT NULL,
        github_repo TEXT NOT NULL,
        docs_paths TEXT DEFAULT 'docs/',
        source_paths TEXT DEFAULT 'src/',
        default_branch TEXT DEFAULT 'main',
        installation_id INTEGER,
        status TEXT DEFAULT 'active',
        total_gaps_found INTEGER DEFAULT 0,
        total_prs_opened INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT REFERENCES projects(id),
        event_type TEXT NOT NULL,
        summary TEXT,
        details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS gaps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT REFERENCES projects(id),
        source_file TEXT NOT NULL,
        gap_type TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'detected',
        pr_number INTEGER,
        pr_url TEXT,
        doc_file TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS api_keys (
        key TEXT PRIMARY KEY,
        project_id TEXT REFERENCES projects(id),
        name TEXT DEFAULT 'default',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS customers (
        id TEXT PRIMARY KEY,
        email TEXT,
        stripe_customer_id TEXT,
        stripe_subscription_id TEXT,
        github_token TEXT,
        plan TEXT DEFAULT 'pro',
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS project_customers (
        project_id TEXT REFERENCES projects(id),
        customer_id TEXT REFERENCES customers(id),
        PRIMARY KEY (project_id, customer_id)
    );
    """)
    conn.commit()
    conn.close()


def create_project(name: str, owner: str, repo: str, docs_paths: str = "docs/",
                   source_paths: str = "src/", default_branch: str = "main") -> dict:
    project_id = str(uuid.uuid4())[:8]
    api_key = f"tome_{uuid.uuid4().hex}"
    conn = get_db()
    conn.execute(
        "INSERT INTO projects (id, name, github_owner, github_repo, docs_paths, source_paths, default_branch) VALUES (?,?,?,?,?,?,?)",
        (project_id, name, owner, repo, docs_paths, source_paths, default_branch)
    )
    conn.execute(
        "INSERT INTO api_keys (key, project_id, name) VALUES (?,?,?)",
        (api_key, project_id, "default")
    )
    conn.commit()
    conn.close()
    return {"id": project_id, "api_key": api_key}


def get_project(project_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_projects() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM projects WHERE status = 'active' ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_activity(project_id: str, event_type: str, summary: str, details: str = None):
    conn = get_db()
    conn.execute(
        "INSERT INTO activity (project_id, event_type, summary, details) VALUES (?,?,?,?)",
        (project_id, event_type, summary, details)
    )
    conn.commit()
    conn.close()


def get_activity(project_id: str, limit: int = 50) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM activity WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
        (project_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_gap(project_id: str, source_file: str, gap_type: str, description: str) -> int:
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO gaps (project_id, source_file, gap_type, description) VALUES (?,?,?,?)",
        (project_id, source_file, gap_type, description)
    )
    gap_id = cursor.lastrowid
    conn.execute(
        "UPDATE projects SET total_gaps_found = total_gaps_found + 1, updated_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), project_id)
    )
    conn.commit()
    conn.close()
    return gap_id


def update_gap(gap_id: int, status: str, pr_number: int = None, pr_url: str = None, doc_file: str = None):
    conn = get_db()
    conn.execute(
        "UPDATE gaps SET status = ?, pr_number = ?, pr_url = ?, doc_file = ?, resolved_at = ? WHERE id = ?",
        (status, pr_number, pr_url, doc_file, datetime.utcnow().isoformat() if status == "resolved" else None, gap_id)
    )
    if pr_url:
        row = conn.execute("SELECT project_id FROM gaps WHERE id = ?", (gap_id,)).fetchone()
        if row:
            conn.execute(
                "UPDATE projects SET total_prs_opened = total_prs_opened + 1, updated_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), row["project_id"])
            )
    conn.commit()
    conn.close()


def get_gaps(project_id: str, status: str = None) -> list[dict]:
    conn = get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM gaps WHERE project_id = ? AND status = ? ORDER BY created_at DESC",
            (project_id, status)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM gaps WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    conn = get_db()
    projects = conn.execute("SELECT COUNT(*) as c FROM projects WHERE status = 'active'").fetchone()["c"]
    gaps = conn.execute("SELECT COUNT(*) as c FROM gaps").fetchone()["c"]
    prs = conn.execute("SELECT COUNT(*) as c FROM gaps WHERE pr_url IS NOT NULL").fetchone()["c"]
    resolved = conn.execute("SELECT COUNT(*) as c FROM gaps WHERE status = 'resolved'").fetchone()["c"]
    conn.close()
    return {
        "total_projects": projects,
        "total_gaps": gaps,
        "total_prs": prs,
        "total_resolved": resolved,
        # Legacy keys for API compat
        "projects": projects,
        "gaps_found": gaps,
        "prs_opened": prs,
        "gaps_resolved": resolved,
    }


def verify_api_key(key: str) -> str | None:
    conn = get_db()
    row = conn.execute("SELECT project_id FROM api_keys WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["project_id"] if row else None


def create_customer(email: str, stripe_customer_id: str = None, stripe_subscription_id: str = None, plan: str = "pro") -> dict:
    customer_id = str(uuid.uuid4())[:8]
    conn = get_db()
    conn.execute(
        "INSERT INTO customers (id, email, stripe_customer_id, stripe_subscription_id, plan) VALUES (?,?,?,?,?)",
        (customer_id, email, stripe_customer_id, stripe_subscription_id, plan)
    )
    conn.commit()
    conn.close()
    return {"id": customer_id, "email": email, "plan": plan}


def get_customer_by_email(email: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM customers WHERE email = ? AND status = 'active'", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_customer_by_stripe_id(stripe_customer_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM customers WHERE stripe_customer_id = ?", (stripe_customer_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_customer_github_token(customer_id: str, github_token: str):
    conn = get_db()
    conn.execute("UPDATE customers SET github_token = ? WHERE id = ?", (github_token, customer_id))
    conn.commit()
    conn.close()


def link_project_to_customer(project_id: str, customer_id: str):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO project_customers (project_id, customer_id) VALUES (?,?)",
                 (project_id, customer_id))
    conn.commit()
    conn.close()


def get_customer_projects(customer_id: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute("""
        SELECT p.* FROM projects p
        JOIN project_customers pc ON p.id = pc.project_id
        WHERE pc.customer_id = ? AND p.status = 'active'
        ORDER BY p.created_at DESC
    """, (customer_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
