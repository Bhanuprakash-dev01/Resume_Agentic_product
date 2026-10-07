# Agentic Product Data Quality Supervisor

This repository contains a Python prototype for a multi-agent product data quality supervisor designed for e-commerce and retail catalogs.

## What it includes

- Supervisor-driven workflow with specialized agents
- Product profiling for missing values, invalid ranges, and schema issues
- Taxonomy validation for misclassified products
- Attribute validation for brands, storage, units, and title normalization
- Duplicate detection and near-duplicate grouping
- RAG-style policy retrieval using a curated product policy corpus
- Evidence-grounded correction generation
- Correction validation with PASS / RETRY / HUMAN_REVIEW / BLOCK outcomes
- Human review routing when risky or low-confidence changes are detected
- Batch quality scoring and summary export

## Project structure

- `product_quality_supervisor/models.py` – core data models for products, findings, and reports
- `product_quality_supervisor/demo_data.py` – synthetic catalog generation and policy corpus
- `product_quality_supervisor/agents/` – focused profiling, taxonomy, attribute validation, duplicate detection, policy retrieval, investigation, correction, validation, human-review, and supervisor modules
- `product_quality_supervisor/workflow.py` – batch workflow and exports
- `product_quality_supervisor/main.py` – command-line runner
- `tests/test_workflow.py` – regression tests for the demo flow

## Usage

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the demo workflow:

```bash
python -m product_quality_supervisor --batch-size 720 --output demo_report.json
```

Run the API server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Deploy to Vercel

Vercel detects the FastAPI application in `app/main.py` automatically. Deploy
from the repository root with the Vercel CLI:

```bash
npx vercel
```

Use `npx vercel --prod` to deploy to production. Review and link the project
when prompted by the CLI.

Vercel functions use temporary SQLite storage at `/tmp/review_store.db`. Reviews
and job records are therefore not durable across function restarts; use a
managed database for persistent production data.

Call the health endpoint:

```bash
curl http://localhost:8000/health
```

Run the tests:

```bash
pytest -q
```

## API endpoints

- `GET /health` – basic health check
- `POST /api/analyze` – analyze a single product payload
- `POST /api/batch` – run synthetic batch analysis and return summary + sample records
- `GET /api/demo` – quick demo summary
- `GET /api/observability/summary` – request, agent, and product-quality measurements
- `GET /api/observability/logs` – structured event logs with filtering and pagination
- `GET /api/observability/logs/export?format=json|csv` – export up to 500 recent log records
- `GET /api/observability/traces` and `/api/observability/traces/{trace_id}` – trace list and span detail
- `GET /api/observability/drift` – baseline/current product-quality drift metrics

## Product-quality observability

The `/observability`, `/logs`, `/metrics`, `/traces`, and `/drift` pages display data
from the observability API. Each HTTP request receives generated request and trace
IDs in the `X-Request-ID` and `X-Trace-ID` response headers. The `data/observability.db`
SQLite database uses WAL mode, foreign keys, and a busy timeout. Workflow spans,
request latency/status, product quality scores, issue/correction counts, policy
retrieval counts, guardrail blocks, and review decisions are persisted without
storing raw product payloads or exception messages.

Drift compares the older and newer halves of the latest 5,000 recorded product
analyses. Categorical PSI and quality-score deltas are marked insufficient until
each cohort has at least 10 records. `cleanup_observability(retention_days=90)` is
available for an operator-controlled retention cleanup; cleanup is not run
automatically.

The prototype does not configure LangGraph, an LLM provider, vector search,
external product tools, authentication, or host-level infrastructure monitoring.
Those metrics are explicitly shown as unavailable, not reported as fabricated
zero-activity integrations. Review identity is still a caller-provided label and
is not authenticated.

Example payload for a single product:

```json
{
  "sku": "SKU-API-001",
  "title": "Apple iphone 15 blk 128",
  "category": "Computer Accessories",
  "brand": "apple",
  "color": null,
  "storage": "128",
  "price": 79999,
  "description": "Example API payload",
  "gtin": "GTIN-001",
  "model": "iPhone 15"
}
```

The web dashboard also provides a product form that submits to `POST /api/analyze`
and displays the returned quality report.

## Request and action guardrails

- The API accepts only product-quality analysis, batch analysis, and review-record
  requests. Unknown request fields and unsupported review decisions are rejected.
- Product text and metadata are treated as input data; the workflow does not
  execute content as instructions or invoke external tools or APIs.
- Analysis produces reports and suggestions only. It does not update product
  records; risky recommendations are routed for human review.
- JSON report exports create new files and refuse to overwrite an existing path.
- Review submissions record a caller-provided reviewer label. Authentication and
  authorization are not configured, so this prototype does not verify reviewer
  identity or treat a stored decision as authenticated approval.

## Production-style deployment architecture

This repository now includes a lightweight deployment layout suitable for a production-ready service:

- FastAPI application layer for request handling
- Supervisor orchestration and agent logic for catalog quality checks
- Synthetic data pipeline for demo and evaluation workloads
- Dockerfile for containerized deployment
- docker-compose configuration for local orchestration
- JSON report export for auditability and downstream review

A more complete production deployment would add:

- PostgreSQL for audit logs and product snapshots
- Redis or Celery for asynchronous batch jobs
- Object storage for exported reports and screenshots
- OAuth / RBAC for human reviewer authentication
- Prometheus + Grafana for observability
- CI/CD pipelines for automated validation and release

## Example decision flow

A record like `Apple iphone 15 blk 128` is analyzed by the profiling, taxonomy, attribute, duplicate, and policy agents. The supervisor aggregates evidence and determines whether the update is safe to auto-fix, requires a suggestion, or needs human review.

## Design notes

The system deliberately models tool-like evidence retrieval and deterministic validation rather than a single monolithic LLM call. That keeps the workflow auditable, structured, and suitable for a human-in-the-loop review model.
