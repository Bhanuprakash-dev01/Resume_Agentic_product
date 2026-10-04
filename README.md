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
- `product_quality_supervisor/agents.py` – specialized agents and orchestration logic
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
