from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "review_store.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _ensure_schema() -> None:
    init_db()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                evidence TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                batch_size INTEGER NOT NULL,
                summary TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


init_db()


def save_review_item(product_id: str, decision: str, reviewer: str, notes: str = "", evidence: Optional[List[str]] = None) -> Dict[str, Any]:
    _ensure_schema()
    evidence_payload = json.dumps(evidence or [])
    created_at = _now_iso()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO review_items (product_id, decision, reviewer, notes, evidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (product_id, decision, reviewer, notes, evidence_payload, created_at),
        )
        conn.commit()
        item_id = cursor.lastrowid

    return {
        "id": item_id,
        "product_id": product_id,
        "decision": decision,
        "reviewer": reviewer,
        "notes": notes,
        "evidence": evidence or [],
        "created_at": created_at,
    }


def list_review_items(limit: int = 50) -> List[Dict[str, Any]]:
    _ensure_schema()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM review_items ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "product_id": row["product_id"],
            "decision": row["decision"],
            "reviewer": row["reviewer"],
            "notes": row["notes"],
            "evidence": json.loads(row["evidence"] or "[]"),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def create_job(job_id: str, batch_size: int, status: str = "queued") -> Dict[str, Any]:
    _ensure_schema()
    now = _now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (job_id, status, batch_size, summary, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, status, batch_size, "{}", now, now),
        )
        conn.commit()
    return {"job_id": job_id, "status": status, "batch_size": batch_size, "summary": {}, "created_at": now, "updated_at": now}


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    _ensure_schema()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    return {
        "job_id": row["job_id"],
        "status": row["status"],
        "batch_size": row["batch_size"],
        "summary": json.loads(row["summary"] or "{}"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def update_job(job_id: str, status: str, summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    _ensure_schema()
    now = _now_iso()
    summary_json = json.dumps(summary or {})
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, summary = ?, updated_at = ? WHERE job_id = ?",
            (status, summary_json, now, job_id),
        )
        conn.commit()
    return get_job(job_id) or {"job_id": job_id, "status": status, "summary": summary or {}}


def get_dashboard_summary() -> Dict[str, Any]:
    _ensure_schema()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT decision, COUNT(*) AS count FROM review_items GROUP BY decision"
        ).fetchall()
        latest_job = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    decisions = {record["decision"]: record["count"] for record in row}
    latest = None
    if latest_job:
        latest = {
            "job_id": latest_job["job_id"],
            "status": latest_job["status"],
            "batch_size": latest_job["batch_size"],
            "summary": json.loads(latest_job["summary"] or "{}"),
            "updated_at": latest_job["updated_at"],
        }
    return {"review_counts": decisions, "latest_job": latest, "review_total": sum(decisions.values())}
