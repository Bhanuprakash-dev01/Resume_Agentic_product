from product_quality_supervisor.demo_data import generate_demo_products
from product_quality_supervisor.models import Correction, ProductRecord
from product_quality_supervisor.workflow import ProductQualityWorkflow
from product_quality_supervisor.agents import ProductQualityValidationAgent


def test_demo_products_cover_issue_mix():
    products = generate_demo_products(200)
    assert len(products) == 200
    assert any("iphone" in item.title.lower() for item in products)
    assert any(item.category != "smartphones" for item in products)


def test_supersivor_detects_quality_issues_for_corrupt_record():
    product = ProductRecord(
        sku="SKU-TEST-001",
        title="Apple iphone 15 blk 128",
        category="Computer Accessories",
        brand="apple",
        color=None,
        storage="128",
        price=79999,
        description="Example with missing color and wrong category.",
        gtin="GTIN-TEST-001",
        model="iPhone 15",
    )
    workflow = ProductQualityWorkflow([product])
    report = workflow.analyze_single_product(product)
    assert report.overall_quality_score < 100
    assert report.requires_human_review or len(report.issues) > 0
    assert len(report.proposed_corrections) > 0


def test_validation_block_on_unsupported_correction():
    agent = ProductQualityValidationAgent()
    product = ProductRecord(
        sku="SKU-TEST-002",
        title="Test product",
        category="smartphones",
        brand="Apple",
        color="Black",
        storage="128 GB",
        price=799,
    )
    correction = Correction(
        field="title",
        original_value=product.title,
        proposed_value="Premium Android Phone",
        mode="AUTO_FIX",
        rationale="High-risk change without support.",
        evidence=[],
        confidence=0.4,
    )
    assert agent.run(product, [correction]) == "BLOCK"
