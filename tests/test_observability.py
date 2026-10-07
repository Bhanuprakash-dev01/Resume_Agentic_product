from datetime import timedelta

from product_quality_supervisor import observability
from product_quality_supervisor.models import ProductRecord
from product_quality_supervisor.workflow import ProductQualityWorkflow


def test_product_analysis_persists_request_spans_and_quality_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(observability, "DB_PATH", tmp_path / "observability.db")
    observability.init_observability_db()
    context = observability.new_request_context("POST", "/api/analyze")
    tokens = observability.activate_context(context)
    try:
        product = ProductRecord(
            sku="SKU-OBS-001",
            title="Apple iphone 15 blk 128",
            category="Computer Accessories",
            brand="apple",
            storage="128",
            price=799,
            model="iPhone 15",
        )
        workflow = ProductQualityWorkflow([product])
        workflow.analyze_single_product(product)
        observability.finish_request(context, 200, observability.perf_counter())
    finally:
        observability.reset_context(tokens)

    summary = observability.get_observability_summary()
    assert summary["requests"]["total"] == 1
    assert summary["product_quality"]["products_analyzed"] == 1
    assert summary["agents"]
    assert summary["capabilities"]["llm"]["available"] is False

    trace = observability.get_trace(context["trace_id"])
    assert trace is not None
    assert trace["request_id"] == context["request_id"]
    assert {span["span_name"] for span in trace["spans"]} >= {
        "POST /api/analyze",
        "Product Analysis",
        "Supervisor",
        "Product Data Profiling",
        "Product Policy Retrieval",
    }
    assert all(span["end_time"] for span in trace["spans"])
    assert observability.get_drift()["overall_status"] == "insufficient_data"


def test_logs_filters_and_retention_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(observability, "DB_PATH", tmp_path / "observability.db")
    observability.init_observability_db()
    context = observability.new_request_context("GET", "/health")
    tokens = observability.activate_context(context)
    try:
        observability.log_event(
            "WARNING",
            "Test guardrail event",
            event_type="guardrail_triggered",
            status="blocked",
            metadata={"guardrail": "request_validation"},
        )
        observability.record_guardrail(
            "request_validation", "blocked", "Test schema failure"
        )
        observability.finish_request(context, 422, observability.perf_counter())
    finally:
        observability.reset_context(tokens)

    result = observability.query_logs(level="WARNING", filters={"endpoint": "/health"})
    assert result["total"] == 1
    assert result["items"][0]["trace_id"] == context["trace_id"]
    assert result["items"][0]["metadata"]["guardrail"] == "request_validation"
    guardrail_logs = observability.query_logs(query="Guardrail decision")
    assert guardrail_logs["total"] == 1
    assert guardrail_logs["items"][0]["event_type"] == "guardrail_triggered"
    assert observability.cleanup_observability(retention_days=90) == 0

    old_timestamp = observability._iso(
        observability._now() - timedelta(days=100)
    )
    with observability._connect() as connection:
        connection.execute(
            "UPDATE traces SET started_at = ? WHERE trace_id = ?",
            (old_timestamp, context["trace_id"]),
        )
        connection.execute("UPDATE application_logs SET timestamp = ?", (old_timestamp,))
        connection.execute("UPDATE request_metrics SET timestamp = ?", (old_timestamp,))
        connection.execute("UPDATE guardrail_events SET timestamp = ?", (old_timestamp,))
        connection.execute("UPDATE error_events SET timestamp = ?", (old_timestamp,))

    assert observability.cleanup_observability(retention_days=90) >= 5
    assert observability.get_trace(context["trace_id"]) is None
    assert observability.query_logs()["total"] == 0
    with observability._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM guardrail_events").fetchone()[0] == 0


def test_population_stability_index_uses_configured_bands():
    stable = observability._psi(["smartphones"] * 20, ["smartphones"] * 20)
    drifted = observability._psi(["smartphones"] * 20, ["laptops"] * 20)

    assert stable == 0
    assert observability._drift_status(stable) == "green"
    assert drifted is not None and drifted > 0.25
    assert observability._drift_status(drifted) == "red"
    assert observability._drift_status(None) == "insufficient_data"
