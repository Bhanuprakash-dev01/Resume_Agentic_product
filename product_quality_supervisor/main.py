from __future__ import annotations

import argparse
import json
from typing import Sequence

from .demo_data import generate_demo_products
from .models import ProductRecord
from .workflow import ProductQualityWorkflow


def run_demo(batch_size: int = 720, output_path: str | None = None) -> dict:
    products = generate_demo_products(batch_size)
    workflow = ProductQualityWorkflow(products)
    reports = workflow.analyze_batch()
    summary = workflow.aggregate_summary(reports)

    if output_path:
        workflow.export_json(reports, output_path)

    payload = {
        "summary": summary,
        "sample": [report.to_dict() for report in reports[:3]],
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic Product Data Quality Supervisor demo")
    parser.add_argument("--batch-size", type=int, default=720, help="Number of synthetic products to generate")
    parser.add_argument("--output", type=str, default=None, help="Optional JSON export path")
    args = parser.parse_args()

    result = run_demo(args.batch_size, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
