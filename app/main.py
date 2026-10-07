from __future__ import annotations

import json
import csv
import io
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db import (
    create_job,
    get_dashboard_summary,
    get_job,
    init_db,
    list_review_items,
    save_review_item,
    update_job,
)
from product_quality_supervisor.demo_data import generate_demo_products
from product_quality_supervisor.models import ProductRecord
from product_quality_supervisor.observability import (
    activate_context,
    finish_request,
    get_drift,
    get_observability_summary,
    get_trace,
    init_observability_db,
    list_traces,
    log_event,
    new_request_context,
    query_logs,
    record_guardrail,
    record_review_event,
    reset_context,
)
from product_quality_supervisor.workflow import ProductQualityWorkflow


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    init_observability_db()
    log_event("INFO", "Application started", event_type="application_started")
    yield
    log_event("INFO", "Application stopped", event_type="application_stopped")


app = FastAPI(
    title="Agentic Product Data Quality Supervisor",
    description="Supervisor-driven product quality analysis for e-commerce catalogs",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def sanitize_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {"type": error["type"], "loc": error["loc"], "msg": error["msg"]}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.middleware("http")
async def observe_http_request(request, call_next):
    context = new_request_context(request.method, request.url.path)
    tokens = activate_context(context)
    started = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = context["request_id"]
        response.headers["X-Trace-ID"] = context["trace_id"]
        if status_code == 422:
            record_guardrail(
                "request_validation",
                "blocked",
                "Request did not satisfy the API schema.",
            )
        return response
    finally:
        finish_request(context, status_code, started)
        reset_context(tokens)


class GuardedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductPayload(GuardedRequest):
    sku: str = Field(max_length=128)
    title: str = Field(max_length=500)
    category: str = Field(max_length=128)
    brand: str = Field(max_length=128)
    color: Optional[str] = Field(default=None, max_length=128)
    storage: Optional[str] = Field(default=None, max_length=128)
    price: Any = None
    weight: Optional[str] = Field(default=None, max_length=128)
    dimensions: Optional[str] = Field(default=None, max_length=128)
    description: str = Field(default="", max_length=10_000)
    gtin: Optional[str] = Field(default=None, max_length=128)
    model: Optional[str] = Field(default=None, max_length=256)
    source: str = Field(default="api", max_length=64)
    metadata: Dict[str, Any] = Field(default_factory=dict, max_length=100)

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        try:
            encoded = json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("metadata must contain only valid JSON values") from exc
        if len(encoded.encode("utf-8")) > 16_384:
            raise ValueError("metadata must be no larger than 16 KiB")
        return value


class BatchRequest(GuardedRequest):
    batch_size: int = Field(default=200, ge=1, le=1000)


class ReviewPayload(GuardedRequest):
    product_id: str = Field(min_length=1, max_length=128)
    decision: Literal["PASS", "RETRY", "HUMAN_REVIEW", "BLOCK", "APPROVE", "REJECT", "MODIFY"]
    reviewer: str = Field(default="system", min_length=1, max_length=128)
    notes: str = Field(default="", max_length=4_000)
    evidence: List[str] = Field(default_factory=list, max_length=50)

    @field_validator("evidence")
    @classmethod
    def validate_evidence_lengths(cls, value: List[str]) -> List[str]:
        if any(len(item) > 1_000 for item in value):
            raise ValueError("each evidence item must be no larger than 1000 characters")
        return value


class BatchJobRequest(GuardedRequest):
    batch_size: int = Field(default=50, ge=1, le=1000)


def _run_batch_job(job_id: str, batch_size: int) -> None:
    update_job(job_id, "processing", {"message": "Running batch quality analysis"})
    products = generate_demo_products(batch_size)
    workflow = ProductQualityWorkflow(products)
    reports = workflow.analyze_batch()
    summary = workflow.aggregate_summary(reports)
    update_job(job_id, "completed", summary)


@app.get("/", include_in_schema=False)
def root() -> HTMLResponse:
    template = Path(__file__).with_name("templates") / "dashboard.html"
    return HTMLResponse(template.read_text(encoding="utf-8"))


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> HTMLResponse:
    template = Path(__file__).with_name("templates") / "dashboard.html"
    return HTMLResponse(template.read_text(encoding="utf-8"))


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "product-quality-supervisor"}


def _observability_page(view: str, trace_id: str = "") -> HTMLResponse:
    template = Path(__file__).with_name("templates") / "observability.html"
    page = template.read_text(encoding="utf-8")
    return HTMLResponse(
        page.replace("__OBSERVABILITY_VIEW__", view).replace("__TRACE_ID__", trace_id)
    )


@app.get("/observability", include_in_schema=False)
def observability_overview() -> HTMLResponse:
    return _observability_page("overview")


@app.get("/logs", include_in_schema=False)
def observability_logs() -> HTMLResponse:
    return _observability_page("logs")


@app.get("/metrics", include_in_schema=False)
def observability_metrics() -> HTMLResponse:
    return _observability_page("metrics")


@app.get("/traces", include_in_schema=False)
def observability_traces() -> HTMLResponse:
    return _observability_page("traces")


@app.get("/traces/{trace_id}", include_in_schema=False)
def observability_trace(trace_id: str) -> HTMLResponse:
    return _observability_page("trace", trace_id)


@app.get("/drift", include_in_schema=False)
def observability_drift() -> HTMLResponse:
    return _observability_page("drift")


@app.get("/api/observability/summary")
def observability_summary() -> Dict[str, Any]:
    return get_observability_summary()


@app.get("/api/observability/logs")
def observability_log_items(
    limit: int = 100,
    offset: int = 0,
    level: Optional[str] = None,
    q: Optional[str] = None,
    environment: Optional[str] = None,
    service: Optional[str] = None,
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    session_id: Optional[str] = None,
    product_id: Optional[str] = None,
    sku: Optional[str] = None,
    agent_name: Optional[str] = None,
    endpoint: Optional[str] = None,
    status: Optional[str] = None,
    error_type: Optional[str] = None,
) -> Dict[str, Any]:
    filters = {
        key: value
        for key, value in {
            "environment": environment,
            "service": service,
            "request_id": request_id,
            "trace_id": trace_id,
            "session_id": session_id,
            "product_id": product_id,
            "sku": sku,
            "agent_name": agent_name,
            "endpoint": endpoint,
            "status": status,
            "error_type": error_type,
        }.items()
        if value is not None
    }
    return query_logs(limit=limit, offset=offset, level=level, query=q, filters=filters)


@app.get("/api/observability/logs/export")
def export_observability_logs(format: Literal["json", "csv"] = "json") -> Response:
    data = query_logs(limit=500)
    if format == "json":
        return Response(
            content=json.dumps(data, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="product-quality-logs.json"'},
        )
    output = io.StringIO()
    fields = [
        "timestamp",
        "level",
        "service",
        "environment",
        "request_id",
        "trace_id",
        "session_id",
        "product_id",
        "sku",
        "agent_name",
        "tool_name",
        "model_name",
        "endpoint",
        "event_type",
        "message",
        "latency_ms",
        "status",
        "error_type",
        "metadata",
        "id",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(data["items"])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="product-quality-logs.csv"'},
    )


@app.get("/api/observability/traces")
def observability_trace_items(limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    return list_traces(limit=limit, offset=offset)


@app.get("/api/observability/traces/{trace_id}")
def observability_trace_detail(trace_id: str) -> Dict[str, Any]:
    item = get_trace(trace_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return item


@app.get("/api/observability/drift")
def observability_drift_metrics() -> Dict[str, Any]:
    return get_drift()


@app.post("/api/analyze")
def analyze_product(payload: ProductPayload) -> Dict[str, Any]:
    record = ProductRecord(**payload.model_dump())
    workflow = ProductQualityWorkflow([record])
    report = workflow.analyze_single_product(record)
    return report.to_dict()


@app.post("/api/batch")
def analyze_batch(request: BatchRequest) -> Dict[str, Any]:
    products = generate_demo_products(request.batch_size)
    workflow = ProductQualityWorkflow(products)
    reports = workflow.analyze_batch()
    summary = workflow.aggregate_summary(reports)
    return {
        "summary": summary,
        "reports": [report.to_dict() for report in reports[:10]],
        "count": len(reports),
    }


@app.get("/api/demo")
def demo_summary() -> Dict[str, Any]:
    products = generate_demo_products(50)
    workflow = ProductQualityWorkflow(products)
    reports = workflow.analyze_batch()
    return workflow.aggregate_summary(reports)


@app.get("/api/dashboard")
def dashboard_summary() -> Dict[str, Any]:
    return get_dashboard_summary()


@app.post("/api/reviews")
def create_review(payload: ReviewPayload) -> Dict[str, Any]:
    item = save_review_item(
        product_id=payload.product_id,
        decision=payload.decision,
        reviewer=payload.reviewer,
        notes=payload.notes,
        evidence=payload.evidence,
    )
    record_review_event(payload.product_id, payload.decision, payload.reviewer)
    return item


@app.get("/api/reviews")
def get_reviews() -> Dict[str, Any]:
    return {"items": list_review_items(limit=20)}


@app.post("/api/jobs/process_batch", status_code=202)
def enqueue_batch_job(request: BatchJobRequest, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    job_id = str(uuid.uuid4())
    job = create_job(job_id, request.batch_size)
    background_tasks.add_task(_run_batch_job, job_id, request.batch_size)
    return {"job_id": job_id, "status": job["status"], "batch_size": request.batch_size}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str) -> Dict[str, Any]:
    item = get_job(job_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return item
