import json

import pytest
from pydantic import ValidationError

from app.main import ProductPayload, ReviewPayload
from product_quality_supervisor.main import run_demo
from product_quality_supervisor.workflow import ProductQualityWorkflow


def test_analysis_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ProductPayload.model_validate(
            {
                "sku": "SKU-GUARD-001",
                "title": "Example product",
                "category": "smartphones",
                "brand": "Apple",
                "unexpected": "ignored before guardrails",
            }
        )


def test_analysis_rejects_oversized_metadata():
    with pytest.raises(ValidationError, match="no larger than 16 KiB"):
        ProductPayload.model_validate(
            {
                "sku": "SKU-GUARD-002",
                "title": "Example product",
                "category": "smartphones",
                "brand": "Apple",
                "metadata": {"description": "x" * 16_385},
            }
        )


def test_review_rejects_unsupported_decision():
    with pytest.raises(ValidationError):
        ReviewPayload.model_validate(
            {
                "product_id": "SKU-GUARD-003",
                "decision": "DELETE_PRODUCT",
            }
        )


@pytest.mark.parametrize("batch_size", [0, 1001])
def test_demo_rejects_batch_size_outside_guardrail(batch_size):
    with pytest.raises(ValueError, match="between 1 and 1000"):
        run_demo(batch_size=batch_size)


def test_export_creates_new_file_and_refuses_overwrite(tmp_path):
    output_path = tmp_path / "report.json"
    workflow = ProductQualityWorkflow([])

    assert workflow.export_json([], str(output_path)) == str(output_path)
    assert json.loads(output_path.read_text(encoding="utf-8")) == {"reports": []}

    output_path.write_text("preserve original", encoding="utf-8")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        workflow.export_json([], str(output_path))

    assert output_path.read_text(encoding="utf-8") == "preserve original"
