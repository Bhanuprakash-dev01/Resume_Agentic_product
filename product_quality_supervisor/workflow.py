from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Sequence

from .agents import SupervisorAgent
from .demo_data import POLICY_DOCS, generate_demo_products
from .models import ProductRecord, QualityReport
from .observability import record_product_report, trace_span


class ProductQualityWorkflow:
    def __init__(self, product_batch: Sequence[ProductRecord] | None = None):
        self.batch = list(product_batch or generate_demo_products())
        self.supervisor = SupervisorAgent(POLICY_DOCS)

    def analyze_single_product(self, product: ProductRecord) -> QualityReport:
        with trace_span(
            "Product Analysis",
            span_type="workflow",
            product_id=product.sku,
            sku=product.sku,
            input_summary={"category": product.category},
        ) as analysis_span:
            report_data = self.supervisor.run(product, self.batch)
            quality_dimensions = report_data["quality_dimensions"]
            overall_score = int(round(sum(quality_dimensions.values()) / max(len(quality_dimensions), 1)))
            report = QualityReport(
                product_id=product.sku,
                overall_quality_score=overall_score,
                quality_dimensions={k: int(v) for k, v in quality_dimensions.items()},
                issues=report_data["issues"],
                proposed_corrections=report_data["proposed_corrections"],
                confidence=float(report_data["confidence"]),
                requires_human_review=bool(report_data["requires_human_review"]),
                decision=report_data["decision"],
                investigation_summary=report_data["investigation_summary"],
                evidence=report_data["evidence"],
            )
            record_product_report(product, report)
            analysis_span["summary"] = {
                "overall_quality_score": report.overall_quality_score,
                "issue_count": len(report.issues),
                "decision": report.decision,
            }
            return report

    def analyze_batch(self) -> List[QualityReport]:
        return [self.analyze_single_product(product) for product in self.batch]

    def aggregate_summary(self, reports: Sequence[QualityReport]) -> Dict[str, Any]:
        avg_score = round(sum(r.overall_quality_score for r in reports) / max(len(reports), 1), 2)
        human_review = sum(1 for r in reports if r.requires_human_review)
        blocked = sum(1 for r in reports if r.decision == "BLOCK")
        auto_fix = sum(1 for r in reports if r.decision == "PASS")
        issue_counts = {}
        for report in reports:
            for issue in report.issues:
                issue_counts[issue["issue_type"]] = issue_counts.get(issue["issue_type"], 0) + 1
        return {
            "product_count": len(reports),
            "average_quality_score": avg_score,
            "human_review_count": human_review,
            "auto_fix_count": auto_fix,
            "blocked_count": blocked,
            "top_issue_types": dict(sorted(issue_counts.items(), key=lambda item: item[1], reverse=True)[:10]),
        }

    def export_json(self, reports: Sequence[QualityReport], file_path: str) -> str:
        payload = {
            "reports": [report.to_dict() for report in reports],
        }
        serialized = json.dumps(payload, indent=2)
        try:
            with open(file_path, "x", encoding="utf-8") as handle:
                handle.write(serialized)
        except FileExistsError as exc:
            raise FileExistsError(f"Refusing to overwrite existing report file: {file_path}") from exc
        return file_path
