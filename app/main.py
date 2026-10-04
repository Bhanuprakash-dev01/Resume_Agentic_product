from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

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
from product_quality_supervisor.workflow import ProductQualityWorkflow

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="Agentic Product Data Quality Supervisor",
    description="Supervisor-driven product quality analysis for e-commerce catalogs",
    version="1.0.0",
    lifespan=lifespan,
)


class ProductPayload(BaseModel):
    sku: str
    title: str
    category: str
    brand: str
    color: Optional[str] = None
    storage: Optional[str] = None
    price: Any = None
    weight: Optional[str] = None
    dimensions: Optional[str] = None
    description: str = ""
    gtin: Optional[str] = None
    model: Optional[str] = None
    source: str = "api"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BatchRequest(BaseModel):
    batch_size: int = Field(default=200, ge=1, le=1000)


class ReviewPayload(BaseModel):
    product_id: str
    decision: str
    reviewer: str = "system"
    notes: str = ""
    evidence: List[str] = Field(default_factory=list)


class BatchJobRequest(BaseModel):
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


@app.post("/api/analyze")
def analyze_product(payload: ProductPayload) -> Dict[str, Any]:
    try:
        record = ProductRecord(**payload.model_dump())
        workflow = ProductQualityWorkflow([record])
        report = workflow.analyze_single_product(record)
        return report.to_dict()
    except Exception as exc:  # pragma: no cover - API guardrail
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
