from __future__ import annotations

import json
import math
import os
import sqlite3
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Dict, Generator, List, Optional

from .models import ProductRecord, QualityReport

DB_PATH = Path(
    os.getenv(
        "OBSERVABILITY_DB_PATH",
        str(Path(__file__).resolve().parent.parent / "data" / "observability.db"),
    )
)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_context: ContextVar[Optional[Dict[str, str]]] = ContextVar("observability_context", default=None)
_parent_span: ContextVar[Optional[str]] = ContextVar("observability_parent_span", default=None)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime] = None) -> str:
    return (value or _now()).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def init_observability_db() -> None:
    with _connect() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                agent_run_id TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                method TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'in_progress',
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_ms REAL,
                product_id TEXT,
                sku TEXT
            );
            CREATE TABLE IF NOT EXISTS spans (
                span_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
                parent_span_id TEXT,
                span_name TEXT NOT NULL,
                span_type TEXT NOT NULL,
                service_name TEXT NOT NULL,
                agent_name TEXT,
                model_name TEXT,
                tool_name TEXT,
                product_id TEXT,
                sku TEXT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_ms REAL,
                status TEXT NOT NULL DEFAULT 'in_progress',
                input_json TEXT NOT NULL DEFAULT '{}',
                output_json TEXT NOT NULL DEFAULT '{}',
                error_type TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS application_logs (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                service TEXT NOT NULL,
                environment TEXT NOT NULL,
                request_id TEXT,
                trace_id TEXT,
                session_id TEXT,
                product_id TEXT,
                sku TEXT,
                agent_name TEXT,
                tool_name TEXT,
                model_name TEXT,
                endpoint TEXT,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                latency_ms REAL,
                status TEXT,
                error_type TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS request_metrics (
                request_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
                method TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                latency_ms REAL NOT NULL,
                environment TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agent_metrics (
                id INTEGER PRIMARY KEY,
                trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
                span_id TEXT NOT NULL UNIQUE REFERENCES spans(span_id) ON DELETE CASCADE,
                agent_run_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS product_quality_metrics (
                id INTEGER PRIMARY KEY,
                trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
                request_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                category TEXT NOT NULL,
                brand TEXT NOT NULL,
                overall_score REAL NOT NULL,
                dimensions_json TEXT NOT NULL,
                decision TEXT NOT NULL,
                confidence REAL NOT NULL,
                requires_human_review INTEGER NOT NULL,
                feature_summary_json TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS product_issue_metrics (
                id INTEGER PRIMARY KEY,
                trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
                product_metric_id INTEGER NOT NULL REFERENCES product_quality_metrics(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                field_name TEXT NOT NULL,
                confidence REAL NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS correction_metrics (
                id INTEGER PRIMARY KEY,
                trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
                product_metric_id INTEGER NOT NULL REFERENCES product_quality_metrics(id) ON DELETE CASCADE,
                product_id TEXT NOT NULL,
                sku TEXT NOT NULL,
                correction_type TEXT NOT NULL,
                field_name TEXT NOT NULL,
                confidence REAL NOT NULL,
                requires_human_review INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rag_metrics (
                id INTEGER PRIMARY KEY,
                trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
                agent_run_id TEXT NOT NULL,
                documents_retrieved INTEGER NOT NULL,
                retrieval_latency_ms REAL NOT NULL,
                has_evidence INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS langgraph_node_metrics (
                id INTEGER PRIMARY KEY,
                trace_id TEXT,
                node_name TEXT NOT NULL,
                node_type TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_ms REAL,
                status TEXT NOT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                error_type TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS guardrail_events (
                id INTEGER PRIMARY KEY,
                request_id TEXT,
                trace_id TEXT,
                product_id TEXT,
                guardrail_name TEXT NOT NULL,
                guardrail_type TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                severity TEXT NOT NULL,
                action_taken TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS human_approval_events (
                id INTEGER PRIMARY KEY,
                request_id TEXT,
                trace_id TEXT,
                product_id TEXT,
                outcome TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                issue_count INTEGER NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS error_events (
                id INTEGER PRIMARY KEY,
                request_id TEXT,
                trace_id TEXT,
                endpoint TEXT,
                error_type TEXT NOT NULL,
                status_code INTEGER,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS system_metrics (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                value REAL NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS llm_metrics (
                id INTEGER PRIMARY KEY,
                trace_id TEXT,
                agent_run_id TEXT,
                model_name TEXT,
                provider TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                latency_ms REAL,
                status TEXT,
                timestamp TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS tool_metrics (
                id INTEGER PRIMARY KEY,
                trace_id TEXT,
                agent_run_id TEXT,
                tool_name TEXT NOT NULL,
                status TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                timestamp TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS token_metrics (
                id INTEGER PRIMARY KEY,
                trace_id TEXT,
                agent_run_id TEXT,
                model_name TEXT,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cost_metrics (
                id INTEGER PRIMARY KEY,
                trace_id TEXT,
                agent_run_id TEXT,
                model_name TEXT,
                cost REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS product_quality_drift (
                id INTEGER PRIMARY KEY,
                feature_name TEXT NOT NULL,
                baseline_value REAL,
                current_value REAL,
                drift_score REAL,
                status TEXT NOT NULL,
                baseline_count INTEGER NOT NULL,
                current_count INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS model_drift (
                id INTEGER PRIMARY KEY,
                metric_name TEXT NOT NULL,
                baseline_value REAL,
                current_value REAL,
                drift_score REAL,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS data_drift (
                id INTEGER PRIMARY KEY,
                feature_name TEXT NOT NULL,
                baseline_value TEXT,
                current_value TEXT,
                drift_score REAL,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS prediction_drift (
                id INTEGER PRIMARY KEY,
                prediction_name TEXT NOT NULL,
                baseline_value REAL,
                current_value REAL,
                drift_score REAL,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS concept_drift (
                id INTEGER PRIMARY KEY,
                metric_name TEXT NOT NULL,
                baseline_value REAL,
                current_value REAL,
                drift_score REAL,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS prompt_drift (
                id INTEGER PRIMARY KEY,
                agent_name TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                drift_score REAL,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS retrieval_drift (
                id INTEGER PRIMARY KEY,
                policy_type TEXT NOT NULL,
                baseline_value REAL,
                current_value REAL,
                drift_score REAL,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY,
                request_id TEXT,
                trace_id TEXT,
                event_type TEXT NOT NULL,
                decision TEXT NOT NULL,
                severity TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS alert_rules (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                metric_name TEXT NOT NULL,
                threshold REAL NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS alert_events (
                id INTEGER PRIMARY KEY,
                rule_id INTEGER REFERENCES alert_rules(id),
                trace_id TEXT,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                resolved_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON application_logs(timestamp);
            CREATE INDEX IF NOT EXISTS idx_logs_request ON application_logs(request_id);
            CREATE INDEX IF NOT EXISTS idx_logs_trace ON application_logs(trace_id);
            CREATE INDEX IF NOT EXISTS idx_logs_session ON application_logs(session_id);
            CREATE INDEX IF NOT EXISTS idx_logs_agent ON application_logs(agent_name);
            CREATE INDEX IF NOT EXISTS idx_logs_endpoint ON application_logs(endpoint);
            CREATE INDEX IF NOT EXISTS idx_traces_timestamp ON traces(started_at);
            CREATE INDEX IF NOT EXISTS idx_traces_request ON traces(request_id);
            CREATE INDEX IF NOT EXISTS idx_traces_session ON traces(session_id);
            CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id);
            CREATE INDEX IF NOT EXISTS idx_spans_agent ON spans(agent_name);
            CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON request_metrics(timestamp);
            CREATE INDEX IF NOT EXISTS idx_product_timestamp ON product_quality_metrics(timestamp);
            CREATE INDEX IF NOT EXISTS idx_product_id ON product_quality_metrics(product_id);
            CREATE INDEX IF NOT EXISTS idx_product_sku ON product_quality_metrics(sku);
            CREATE INDEX IF NOT EXISTS idx_issue_type ON product_issue_metrics(issue_type);
            CREATE INDEX IF NOT EXISTS idx_correction_type ON correction_metrics(correction_type);
            CREATE INDEX IF NOT EXISTS idx_agents_name ON agent_metrics(agent_name);
            CREATE INDEX IF NOT EXISTS idx_llm_model ON llm_metrics(model_name);
            CREATE INDEX IF NOT EXISTS idx_tools_name ON tool_metrics(tool_name);
            CREATE INDEX IF NOT EXISTS idx_langgraph_node_timestamp ON langgraph_node_metrics(start_time);
            CREATE INDEX IF NOT EXISTS idx_model_drift_timestamp ON model_drift(timestamp);
            CREATE INDEX IF NOT EXISTS idx_data_drift_timestamp ON data_drift(timestamp);
            CREATE INDEX IF NOT EXISTS idx_prediction_drift_timestamp ON prediction_drift(timestamp);
            CREATE INDEX IF NOT EXISTS idx_concept_drift_timestamp ON concept_drift(timestamp);
            CREATE INDEX IF NOT EXISTS idx_prompt_drift_timestamp ON prompt_drift(timestamp);
            CREATE INDEX IF NOT EXISTS idx_retrieval_drift_timestamp ON retrieval_drift(timestamp);
            CREATE INDEX IF NOT EXISTS idx_guardrail_timestamp ON guardrail_events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_approval_timestamp ON human_approval_events(timestamp);
            """
        )


def new_request_context(method: str, endpoint: str) -> Dict[str, str]:
    context = {
        "request_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "workflow_id": str(uuid.uuid4()),
        "agent_run_id": str(uuid.uuid4()),
        "root_span_id": str(uuid.uuid4()),
        "endpoint": endpoint,
        "method": method,
    }
    now = _iso()
    with _connect() as connection:
        connection.execute(
            """INSERT INTO traces
            (trace_id, request_id, session_id, user_id, conversation_id, workflow_id,
             agent_run_id, endpoint, method, started_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                context["trace_id"],
                context["request_id"],
                context["session_id"],
                context["user_id"],
                context["conversation_id"],
                context["workflow_id"],
                context["agent_run_id"],
                endpoint,
                method,
                now,
            ),
        )
        connection.execute(
            """INSERT INTO spans
            (span_id, trace_id, span_name, span_type, service_name, start_time, input_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                context["root_span_id"],
                context["trace_id"],
                f"{method} {endpoint}",
                "request",
                "product-quality-supervisor",
                now,
                _json({"method": method, "endpoint": endpoint}),
            ),
        )
    return context


def activate_context(context: Dict[str, str]) -> tuple[Token, Token]:
    return _context.set(context), _parent_span.set(context["root_span_id"])


def reset_context(tokens: tuple[Token, Token]) -> None:
    _parent_span.reset(tokens[1])
    _context.reset(tokens[0])


def current_context() -> Optional[Dict[str, str]]:
    return _context.get()


@contextmanager
def trace_span(
    span_name: str,
    *,
    span_type: str = "agent",
    agent_name: Optional[str] = None,
    product_id: Optional[str] = None,
    sku: Optional[str] = None,
    input_summary: Optional[Dict[str, Any]] = None,
) -> Generator[Dict[str, Any], None, None]:
    context = _context.get()
    if context is None:
        yield {}
        return

    span_id = str(uuid.uuid4())
    started = _now()
    parent_id = _parent_span.get() or context["root_span_id"]
    with _connect() as connection:
        connection.execute(
            """INSERT INTO spans
            (span_id, trace_id, parent_span_id, span_name, span_type, service_name,
             agent_name, product_id, sku, start_time, input_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                span_id,
                context["trace_id"],
                parent_id,
                span_name,
                span_type,
                "product-quality-supervisor",
                agent_name,
                product_id,
                sku,
                _iso(started),
                _json(input_summary or {}),
            ),
        )
    parent_token = _parent_span.set(span_id)
    result: Dict[str, Any] = {}
    error_type: Optional[str] = None
    status = "completed"
    try:
        yield result
    except Exception as exc:
        status = "failed"
        error_type = type(exc).__name__
        raise
    finally:
        ended = _now()
        duration = (ended - started).total_seconds() * 1000
        output_summary = result.get("summary", {})
        with _connect() as connection:
            connection.execute(
                """UPDATE spans SET end_time = ?, duration_ms = ?, status = ?,
                   output_json = ?, error_type = ? WHERE span_id = ?""",
                (_iso(ended), duration, status, _json(output_summary), error_type, span_id),
            )
            if agent_name:
                connection.execute(
                    """INSERT INTO agent_metrics
                    (trace_id, span_id, agent_run_id, agent_name, status, duration_ms, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        context["trace_id"],
                        span_id,
                        context["agent_run_id"],
                        agent_name,
                        status,
                        duration,
                        _iso(ended),
                    ),
                )
            if error_type:
                connection.execute(
                    """INSERT INTO error_events
                    (request_id, trace_id, endpoint, error_type, timestamp)
                    VALUES (?, ?, ?, ?, ?)""",
                    (context["request_id"], context["trace_id"], context["endpoint"], error_type, _iso(ended)),
                )
        log_event(
            "ERROR" if error_type else "INFO",
            "Workflow span failed" if error_type else "Workflow span completed",
            event_type="agent_failed" if error_type else "agent_completed",
            status=status,
            error_type=error_type,
            agent_name=agent_name,
            product_id=product_id,
            sku=sku,
            latency_ms=duration,
            metadata={"span_name": span_name},
        )
        _parent_span.reset(parent_token)


def log_event(
    level: str,
    message: str,
    *,
    event_type: str,
    status: Optional[str] = None,
    error_type: Optional[str] = None,
    agent_name: Optional[str] = None,
    product_id: Optional[str] = None,
    sku: Optional[str] = None,
    latency_ms: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    context = _context.get()
    with _connect() as connection:
        connection.execute(
            """INSERT INTO application_logs
            (timestamp, level, service, environment, request_id, trace_id, session_id,
             product_id, sku, agent_name, endpoint, event_type, message, latency_ms,
             status, error_type, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _iso(),
                level.upper(),
                "product-quality-supervisor",
                os.getenv("APP_ENV", "development"),
                context.get("request_id") if context else None,
                context.get("trace_id") if context else None,
                context.get("session_id") if context else None,
                product_id,
                sku,
                agent_name,
                context.get("endpoint") if context else None,
                event_type,
                message,
                latency_ms,
                status,
                error_type,
                _json(metadata or {}),
            ),
        )


def finish_request(context: Dict[str, str], status_code: int, started: float) -> float:
    duration = (perf_counter() - started) * 1000
    ended = _now()
    status = "completed" if status_code < 400 else "failed"
    with _connect() as connection:
        connection.execute(
            "UPDATE traces SET status = ?, ended_at = ?, duration_ms = ? WHERE trace_id = ?",
            (status, _iso(ended), duration, context["trace_id"]),
        )
        connection.execute(
            """UPDATE spans SET end_time = ?, duration_ms = ?, status = ?, output_json = ?
               WHERE span_id = ?""",
            (_iso(ended), duration, status, _json({"status_code": status_code}), context["root_span_id"]),
        )
        connection.execute(
            """INSERT INTO request_metrics
            (request_id, trace_id, method, endpoint, status_code, latency_ms, environment, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                context["request_id"],
                context["trace_id"],
                context["method"],
                context["endpoint"],
                status_code,
                duration,
                os.getenv("APP_ENV", "development"),
                _iso(ended),
            ),
        )
        if status_code >= 400:
            connection.execute(
                """INSERT INTO error_events
                (request_id, trace_id, endpoint, error_type, status_code, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    context["request_id"],
                    context["trace_id"],
                    context["endpoint"],
                    "http_error",
                    status_code,
                    _iso(ended),
                ),
            )
    log_event(
        "ERROR" if status_code >= 400 else "INFO",
        "HTTP request failed" if status_code >= 400 else "HTTP request completed",
        event_type="request_failed" if status_code >= 400 else "request_completed",
        status=str(status_code),
        latency_ms=duration,
    )
    return duration


def record_product_report(product: ProductRecord, report: QualityReport) -> None:
    context = _context.get()
    if not context:
        return
    timestamp = _iso()
    feature_summary = {
        "title_length": len(product.title or ""),
        "description_length": len(product.description or ""),
        "has_color": bool(product.color),
        "has_storage": bool(product.storage),
        "has_gtin": bool(product.gtin),
        "has_model": bool(product.model),
        "price_bucket": _price_bucket(product.price),
    }
    with _connect() as connection:
        connection.execute(
            "UPDATE traces SET product_id = ?, sku = ? WHERE trace_id = ?",
            (product.sku, product.sku, context["trace_id"]),
        )
        cursor = connection.execute(
            """INSERT INTO product_quality_metrics
            (trace_id, request_id, product_id, sku, category, brand, overall_score,
             dimensions_json, decision, confidence, requires_human_review,
             feature_summary_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                context["trace_id"],
                context["request_id"],
                product.sku,
                product.sku,
                product.category,
                product.brand,
                report.overall_quality_score,
                _json(report.quality_dimensions),
                report.decision,
                report.confidence,
                int(report.requires_human_review),
                _json(feature_summary),
                timestamp,
            ),
        )
        metric_id = cursor.lastrowid
        for issue in report.issues:
            connection.execute(
                """INSERT INTO product_issue_metrics
                (trace_id, product_metric_id, product_id, sku, issue_type,
                 severity, field_name, confidence, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    context["trace_id"],
                    metric_id,
                    product.sku,
                    product.sku,
                    issue.get("issue_type", "unknown"),
                    issue.get("severity", "unknown"),
                    issue.get("field", "unknown"),
                    float(issue.get("confidence", 0)),
                    timestamp,
                ),
            )
        for correction in report.proposed_corrections:
            connection.execute(
                """INSERT INTO correction_metrics
                (trace_id, product_metric_id, product_id, sku, correction_type,
                 field_name, confidence, requires_human_review, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    context["trace_id"],
                    metric_id,
                    product.sku,
                    product.sku,
                    correction.get("mode", "unknown"),
                    correction.get("field", "unknown"),
                    float(correction.get("confidence", 0)),
                    int(bool(correction.get("requires_human_review"))),
                    timestamp,
                ),
            )
        if report.requires_human_review:
            connection.execute(
                """INSERT INTO human_approval_events
                (request_id, trace_id, product_id, outcome, reviewer, issue_count, timestamp)
                VALUES (?, ?, ?, 'requested', 'unassigned', ?, ?)""",
                (context["request_id"], context["trace_id"], product.sku, len(report.issues), timestamp),
            )
    if report.decision == "BLOCK":
        record_guardrail(
            "correction_evidence",
            "blocked",
            "Correction validation blocked the proposed change.",
            severity="high",
        )


def _price_bucket(value: Any) -> str:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return "missing_or_invalid"
    if price < 100:
        return "under_100"
    if price < 500:
        return "100_to_499"
    if price < 2000:
        return "500_to_1999"
    return "2000_plus"


def record_review_event(product_id: str, decision: str, reviewer: str) -> None:
    context = _context.get()
    with _connect() as connection:
        connection.execute(
            """INSERT INTO human_approval_events
            (request_id, trace_id, product_id, outcome, reviewer, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                context.get("request_id") if context else None,
                context.get("trace_id") if context else None,
                product_id,
                decision.lower(),
                reviewer,
                _iso(),
            ),
        )


def record_guardrail(name: str, decision: str, reason: str, severity: str = "warning") -> None:
    context = _context.get()
    with _connect() as connection:
        connection.execute(
            """INSERT INTO guardrail_events
            (request_id, trace_id, guardrail_name, guardrail_type, decision,
             reason, severity, action_taken, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                context.get("request_id") if context else None,
                context.get("trace_id") if context else None,
                name,
                "input",
                decision,
                reason,
                severity,
                "rejected" if decision == "blocked" else "allowed",
                _iso(),
            ),
        )
    log_event(
        "WARNING" if decision != "blocked" else "ERROR",
        f"Guardrail decision: {name}",
        event_type="guardrail_triggered",
        status=decision,
        error_type="request_validation" if decision == "blocked" else None,
        metadata={"severity": severity},
    )


def record_rag_retrieval(documents_retrieved: int, latency_ms: float, has_evidence: bool) -> None:
    context = _context.get()
    if not context:
        return
    with _connect() as connection:
        connection.execute(
            """INSERT INTO rag_metrics
            (trace_id, agent_run_id, documents_retrieved, retrieval_latency_ms, has_evidence, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                context["trace_id"],
                context["agent_run_id"],
                documents_retrieved,
                latency_ms,
                int(has_evidence),
                _iso(),
            ),
        )


def _rows(connection: sqlite3.Connection, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, params).fetchall()]


def get_observability_summary() -> Dict[str, Any]:
    with _connect() as connection:
        requests = _rows(connection, "SELECT status_code, latency_ms FROM request_metrics ORDER BY timestamp DESC LIMIT 10000")
        product_rows = _rows(connection, "SELECT * FROM product_quality_metrics ORDER BY timestamp DESC LIMIT 10000")
        issues = _rows(connection, "SELECT issue_type, severity, COUNT(*) AS count FROM product_issue_metrics GROUP BY issue_type, severity")
        issue_severities = _rows(
            connection,
            "SELECT severity, COUNT(*) AS count FROM product_issue_metrics GROUP BY severity",
        )
        decisions = _rows(
            connection,
            "SELECT decision, COUNT(*) AS count FROM product_quality_metrics GROUP BY decision",
        )
        agents = _rows(
            connection,
            """SELECT agent_name, COUNT(*) AS runs,
               AVG(duration_ms) AS average_duration_ms,
               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failures
               FROM agent_metrics GROUP BY agent_name ORDER BY runs DESC""",
        )
        corrections = _rows(
            connection,
            "SELECT correction_type, COUNT(*) AS count FROM correction_metrics GROUP BY correction_type",
        )
        approvals = _rows(
            connection,
            "SELECT outcome, COUNT(*) AS count FROM human_approval_events GROUP BY outcome",
        )
        guardrails = _rows(
            connection,
            "SELECT decision, COUNT(*) AS count FROM guardrail_events GROUP BY decision",
        )
        error_count = connection.execute("SELECT COUNT(*) FROM error_events").fetchone()[0]
        log_count = connection.execute("SELECT COUNT(*) FROM application_logs").fetchone()[0]
        trace_count = connection.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        products_with_issues = connection.execute(
            """SELECT COUNT(DISTINCT product_metric_id) FROM product_issue_metrics
               WHERE product_metric_id IN (SELECT id FROM product_quality_metrics
                   ORDER BY timestamp DESC LIMIT 10000)"""
        ).fetchone()[0]
        timestamp_rows = _rows(
            connection,
            "SELECT timestamp FROM request_metrics ORDER BY timestamp DESC LIMIT 10000",
        )

    status_success = sum(1 for row in requests if row["status_code"] < 400)
    latencies = sorted(float(row["latency_ms"]) for row in requests)
    quality_scores = [float(row["overall_score"]) for row in product_rows]
    issue_totals: Dict[str, int] = {}
    for row in issues:
        issue_totals[row["issue_type"]] = issue_totals.get(row["issue_type"], 0) + int(row["count"])
    score_dimensions: Dict[str, float] = {}
    for row in product_rows:
        for name, score in json.loads(row["dimensions_json"]).items():
            score_dimensions[name] = score_dimensions.get(name, 0) + float(score)
    if product_rows:
        score_dimensions = {key: round(value / len(product_rows), 2) for key, value in score_dimensions.items()}
    request_total = len(requests)
    now = _now()
    requests_per_minute = 0
    requests_per_hour = 0
    requests_per_day = 0
    for row in timestamp_rows:
        try:
            timestamp = datetime.fromisoformat(row["timestamp"])
        except ValueError:
            continue
        age = now - timestamp
        if age <= timedelta(minutes=1):
            requests_per_minute += 1
        if age <= timedelta(hours=1):
            requests_per_hour += 1
        if age <= timedelta(days=1):
            requests_per_day += 1
    slowest_agent = max(agents, key=lambda item: item["average_duration_ms"] or 0, default=None)
    most_used_agent = max(agents, key=lambda item: item["runs"], default=None)
    highest_failure_agent = max(agents, key=lambda item: item["failures"], default=None)
    return {
        "requests": {
            "total": request_total,
            "successful": status_success,
            "failed": request_total - status_success,
            "success_rate": round(status_success / request_total, 4) if request_total else None,
            "failure_rate": round((request_total - status_success) / request_total, 4) if request_total else None,
            "per_minute": requests_per_minute,
            "per_hour": requests_per_hour,
            "per_day": requests_per_day,
            "average_latency_ms": round(mean(latencies), 2) if latencies else None,
            "p50_latency_ms": _percentile(latencies, 0.50),
            "p75_latency_ms": _percentile(latencies, 0.75),
            "p90_latency_ms": _percentile(latencies, 0.90),
            "p95_latency_ms": _percentile(latencies, 0.95),
            "p99_latency_ms": _percentile(latencies, 0.99),
            "maximum_latency_ms": max(latencies) if latencies else None,
        },
        "product_quality": {
            "products_analyzed": len(product_rows),
            "clean_products": max(0, len(product_rows) - products_with_issues),
            "products_with_issues": products_with_issues,
            "total_issues": sum(issue_totals.values()),
            "issues_by_severity": {row["severity"]: row["count"] for row in issue_severities},
            "average_quality_score": round(mean(quality_scores), 2) if quality_scores else None,
            "average_dimensions": score_dimensions,
            "issues_by_type": issue_totals,
            "corrections_by_type": {row["correction_type"]: row["count"] for row in corrections},
            "human_review_count": sum(row["requires_human_review"] for row in product_rows),
            "decisions": {row["decision"]: row["count"] for row in decisions},
            "average_correction_confidence": _average_correction_confidence(),
        },
        "agents": agents,
        "agent_highlights": {
            "slowest_agent": slowest_agent,
            "most_used_agent": most_used_agent,
            "highest_failure_agent": highest_failure_agent,
        },
        "approvals": {row["outcome"]: row["count"] for row in approvals},
        "guardrails": {row["decision"]: row["count"] for row in guardrails},
        "errors": error_count,
        "logs": log_count,
        "traces": trace_count,
        "capabilities": {
            "llm": {"available": False, "reason": "No LLM provider is configured."},
            "langgraph": {"available": False, "reason": "The workflow currently uses the in-repository Python supervisor."},
            "vector_search": {"available": False, "reason": "Policy retrieval is local keyword matching, not vector search."},
            "external_tools": {"available": False, "reason": "No external product or taxonomy tools are configured."},
            "infrastructure_metrics": {"available": False, "reason": "Host-level metrics collection is not configured."},
        },
    }


def _average_correction_confidence() -> Optional[float]:
    with _connect() as connection:
        row = connection.execute("SELECT AVG(confidence) FROM correction_metrics").fetchone()
    return round(float(row[0]), 4) if row[0] is not None else None


def _percentile(values: List[float], percentile: float) -> Optional[float]:
    if not values:
        return None
    index = min(len(values) - 1, max(0, round((len(values) - 1) * percentile)))
    return round(values[index], 2)


def query_logs(
    *,
    limit: int = 100,
    offset: int = 0,
    level: Optional[str] = None,
    query: Optional[str] = None,
    filters: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    limit = min(max(limit, 1), 500)
    offset = max(offset, 0)
    conditions: List[str] = []
    params: List[Any] = []
    if level:
        conditions.append("level = ?")
        params.append(level.upper())
    if query:
        pattern = f"%{query[:100]}%"
        conditions.append("(message LIKE ? OR event_type LIKE ? OR request_id LIKE ? OR trace_id LIKE ? OR sku LIKE ?)")
        params.extend([pattern] * 5)
    allowed_filters = {
        "environment",
        "service",
        "request_id",
        "trace_id",
        "session_id",
        "product_id",
        "sku",
        "agent_name",
        "endpoint",
        "status",
        "error_type",
    }
    for column, value in (filters or {}).items():
        if column in allowed_filters and value:
            conditions.append(f"{column} = ?")
            params.append(value[:128])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with _connect() as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM application_logs {where}", params).fetchone()[0]
        items = _rows(
            connection,
            f"SELECT * FROM application_logs {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            tuple(params + [limit, offset]),
        )
    for item in items:
        item["metadata"] = json.loads(item.pop("metadata_json"))
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def list_traces(limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    limit = min(max(limit, 1), 500)
    offset = max(offset, 0)
    with _connect() as connection:
        total = connection.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        items = _rows(connection, "SELECT * FROM traces ORDER BY started_at DESC LIMIT ? OFFSET ?", (limit, offset))
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_trace(trace_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,)).fetchone()
        if row is None:
            return None
        trace = dict(row)
        spans = _rows(connection, "SELECT * FROM spans WHERE trace_id = ? ORDER BY start_time", (trace_id,))
    for span in spans:
        span["input"] = json.loads(span.pop("input_json"))
        span["output"] = json.loads(span.pop("output_json"))
        span["metadata"] = json.loads(span.pop("metadata_json"))
    trace["spans"] = spans
    return trace


def _psi(baseline: List[str], current: List[str]) -> Optional[float]:
    if len(baseline) < 10 or len(current) < 10:
        return None
    categories = set(baseline) | set(current)
    base_total, current_total = len(baseline), len(current)
    epsilon = 1e-6
    score = 0.0
    for category in categories:
        base_rate = max(baseline.count(category) / base_total, epsilon)
        current_rate = max(current.count(category) / current_total, epsilon)
        score += (current_rate - base_rate) * math.log(current_rate / base_rate)
    return round(score, 6)


def get_drift() -> Dict[str, Any]:
    with _connect() as connection:
        rows = _rows(
            connection,
            "SELECT * FROM product_quality_metrics ORDER BY timestamp DESC LIMIT 5000",
        )
    rows.reverse()
    split = max(1, len(rows) // 2)
    baseline, current = rows[:split], rows[split:]
    metrics: List[Dict[str, Any]] = []
    for name in ("category", "brand", "decision"):
        baseline_values = [str(row[name]) for row in baseline]
        current_values = [str(row[name]) for row in current]
        score = _psi(baseline_values, current_values)
        metrics.append(
            {
                "feature": name,
                "method": "population_stability_index",
                "score": score,
                "status": _drift_status(score),
                "baseline_count": len(baseline),
                "current_count": len(current),
                "baseline_distribution": _distribution(baseline_values),
                "current_distribution": _distribution(current_values),
            }
        )

    baseline_scores = [float(row["overall_score"]) for row in baseline]
    current_scores = [float(row["overall_score"]) for row in current]
    if len(baseline_scores) >= 10 and len(current_scores) >= 10:
        score_delta = round(mean(current_scores) - mean(baseline_scores), 2)
        quality_status = "red" if abs(score_delta) >= 15 else "amber" if abs(score_delta) >= 7 else "green"
    else:
        score_delta = None
        quality_status = "insufficient_data"
    metrics.append(
        {
            "feature": "average_quality_score",
            "method": "baseline_current_mean_delta",
            "baseline_value": round(mean(baseline_scores), 2) if baseline_scores else None,
            "current_value": round(mean(current_scores), 2) if current_scores else None,
            "score": score_delta,
            "status": quality_status,
            "baseline_count": len(baseline),
            "current_count": len(current),
        }
    )
    statuses = [item["status"] for item in metrics if item["status"] != "insufficient_data"]
    overall = "red" if "red" in statuses else "amber" if "amber" in statuses else "green" if statuses else "insufficient_data"
    return {
        "overall_status": overall,
        "baseline_definition": "Older half of the latest 5,000 product analyses",
        "current_definition": "Newer half of the latest 5,000 product analyses",
        "sample_count": len(rows),
        "metrics": metrics,
        "note": "Drift is not statistically assessed until both cohorts contain at least 10 records.",
    }


def _drift_status(score: Optional[float]) -> str:
    if score is None:
        return "insufficient_data"
    return "red" if score > 0.25 else "amber" if score >= 0.10 else "green"


def _distribution(values: List[str]) -> Dict[str, float]:
    if not values:
        return {}
    counts: Dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return {key: round(count / len(values), 4) for key, count in counts.items()}


def cleanup_observability(retention_days: int = 90) -> int:
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    cutoff = _iso(_now() - timedelta(days=retention_days))
    deleted = 0
    with _connect() as connection:
        for table, timestamp_column in (
            ("application_logs", "timestamp"),
            ("request_metrics", "timestamp"),
            ("traces", "started_at"),
            ("system_metrics", "timestamp"),
            ("llm_metrics", "timestamp"),
            ("tool_metrics", "timestamp"),
            ("token_metrics", "timestamp"),
            ("cost_metrics", "timestamp"),
            ("langgraph_node_metrics", "start_time"),
            ("guardrail_events", "timestamp"),
            ("human_approval_events", "timestamp"),
            ("error_events", "timestamp"),
            ("product_quality_drift", "timestamp"),
            ("model_drift", "timestamp"),
            ("data_drift", "timestamp"),
            ("prediction_drift", "timestamp"),
            ("concept_drift", "timestamp"),
            ("prompt_drift", "timestamp"),
            ("retrieval_drift", "timestamp"),
            ("alert_events", "timestamp"),
        ):
            cursor = connection.execute(
                f"DELETE FROM {table} WHERE {timestamp_column} < ?",
                (cutoff,),
            )
            deleted += cursor.rowcount
    return deleted
