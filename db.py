"""
db.py — SQLite persistence layer for the GTM Research Copilot.

Stores leads, their scores, enrichment data, outreach drafts, and a
suppression list. Uses WAL mode for better concurrent read/write performance.

Tables:
    leads            id, company, domain (UNIQUE dedupe key), website,
                     industry, description, posting_text, company_context,
                     source, fit_score_rule, fit_score_llm, fit_score_final,
                     fit_reason, contact_name, contact_title, email,
                     email_confidence, linkedin_url, draft_email_body,
                     linkedin_note, status, created_at
    suppression_list email_or_domain UNIQUE, reason, created_at

Status funnel: new -> qualified -> enriched -> drafted -> draft_created ->
sent -> replied / rejected / skipped
"""

import sqlite3
from contextlib import contextmanager
from typing import Any


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_LEADS_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    domain TEXT NOT NULL UNIQUE,
    website TEXT,
    industry TEXT,
    description TEXT,
    posting_text TEXT,
    company_context TEXT,
    source TEXT,
    fit_score_rule INTEGER DEFAULT 0,
    fit_score_llm INTEGER DEFAULT NULL,
    fit_score_final INTEGER DEFAULT NULL,
    fit_reason TEXT,
    contact_name TEXT,
    contact_title TEXT,
    email TEXT,
    email_confidence TEXT DEFAULT 'not_found',
    linkedin_url TEXT,
    draft_email_body TEXT,
    linkedin_note TEXT,
    gmail_draft_id TEXT,
    status TEXT DEFAULT 'new',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

_SUPPRESSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS suppression_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_or_domain TEXT NOT NULL UNIQUE,
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_leads_domain ON leads(domain);",
    "CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);",
    "CREATE INDEX IF NOT EXISTS idx_leads_industry ON leads(industry);",
    "CREATE INDEX IF NOT EXISTS idx_suppression_email_domain ON suppression_list(email_or_domain);",
]


def get_conn(db_path: str = "leads.db") -> sqlite3.Connection:
    """
    Open a connection to the SQLite database with WAL mode enabled.

    WAL mode allows concurrent readers and a single writer, which is ideal
    for a Streamlit app that reads leads while a background pipeline writes.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(_LEADS_SCHEMA)
    conn.executescript(_SUPPRESSION_SCHEMA)
    for stmt in _INDEXES:
        conn.execute(stmt)
    conn.commit()
    return conn


@contextmanager
def transaction(db_path: str = "leads.db"):
    """
    Context manager for a transactional database connection.

    Usage:
        with transaction(db_path) as conn:
            conn.execute("INSERT INTO leads (...) VALUES (...)")
    """
    conn = get_conn(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Lead CRUD
# ---------------------------------------------------------------------------


def upsert_lead(
    conn: sqlite3.Connection,
    domain: str,
    **fields: Any,
) -> int:
    """
    Insert a new lead or update an existing one matched by `domain`.

    Returns the lead's primary key `id`.
    """
    cur = conn.execute("SELECT id FROM leads WHERE domain = ?", (domain,))
    row = cur.fetchone()

    if row:
        lead_id = row["id"]
        set_parts = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [lead_id]
        conn.execute(
            f"UPDATE leads SET {set_parts} WHERE id = ?", values
        )
        return lead_id

    # Insert new lead; only known columns are allowed.
    allowed = {
        "company", "domain", "website", "industry", "description",
        "posting_text", "company_context", "source", "fit_score_rule",
        "fit_score_llm", "fit_score_final", "fit_reason", "contact_name",
        "contact_title", "email", "email_confidence", "linkedin_url",
        "draft_email_body", "linkedin_note", "status", "created_at",
        "gmail_draft_id",
    }
    insert_fields = {k: v for k, v in fields.items() if k in allowed}
    insert_fields["domain"] = domain
    columns = ", ".join(insert_fields.keys())
    placeholders = ", ".join("?" for _ in insert_fields)
    values = list(insert_fields.values())
    cur = conn.execute(
        f"INSERT INTO leads ({columns}) VALUES ({placeholders})", values
    )
    return cur.lastrowid


def get_lead(conn: sqlite3.Connection, lead_id: int) -> dict | None:
    """Return a single lead by its primary key id, or None if not found."""
    cur = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def get_lead_by_domain(conn: sqlite3.Connection, domain: str) -> dict | None:
    """Return a single lead by its domain, or None if not found."""
    cur = conn.execute("SELECT * FROM leads WHERE domain = ?", (domain,))
    row = cur.fetchone()
    return dict(row) if row else None


def query_leads(
    conn: sqlite3.Connection,
    filters: dict[str, Any] | None = None,
    order_by: str = "created_at DESC",
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict]:
    """
    Query leads with optional filters.

    Supported filter keys: status, industry, min_fit_score, search (matches
    company or domain), email_confidence.
    """
    sql = "SELECT * FROM leads"
    params: list[Any] = []
    where_clauses: list[str] = []

    if filters:
        if "status" in filters:
            where_clauses.append("status = ?")
            params.append(filters["status"])
        if "industry" in filters:
            where_clauses.append("industry = ?")
            params.append(filters["industry"])
        if "email_confidence" in filters:
            where_clauses.append("email_confidence = ?")
            params.append(filters["email_confidence"])
        if "min_fit_score" in filters:
            where_clauses.append(
                "COALESCE(fit_score_final, fit_score_rule) >= ?"
            )
            params.append(filters["min_fit_score"])
        if "search" in filters:
            where_clauses.append(
                "(company LIKE ? OR domain LIKE ?)"
            )
            like = f"%{filters['search']}%"
            params.extend([like, like])

    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    if offset is not None:
        sql += f" OFFSET {int(offset)}"

    cur = conn.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def count_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    """Return a dict mapping each status value to its lead count."""
    cur = conn.execute(
        "SELECT status, COUNT(*) as c FROM leads GROUP BY status"
    )
    return {row["status"]: row["c"] for row in cur.fetchall()}


# ---------------------------------------------------------------------------
# Suppression list
# ---------------------------------------------------------------------------


def is_suppressed(conn: sqlite3.Connection, email_or_domain: str) -> bool:
    """Return True if the given email or domain is on the suppression list."""
    cur = conn.execute(
        "SELECT 1 FROM suppression_list WHERE email_or_domain = ?",
        (email_or_domain,),
    )
    return cur.fetchone() is not None


def add_to_suppression(
    conn: sqlite3.Connection,
    email_or_domain: str,
    reason: str,
) -> None:
    """Add an email or domain to the suppression list."""
    conn.execute(
        "INSERT OR IGNORE INTO suppression_list (email_or_domain, reason) "
        "VALUES (?, ?)",
        (email_or_domain, reason),
    )