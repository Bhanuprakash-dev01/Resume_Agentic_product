from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Sequence

from .agents import SupervisorAgent
from .demo_data import POLICY_DOCS, generate_demo_products
from .models import ProductRecord, QualityReport


class ProductQualityWorkflow:
    def __init__(self, product_batch: Sequence[ProductRecord] | None = None):
        self.batch = list(product_batch or generate_demo_products())
        self.supervisor = SupervisorAgent(POLICY_DOCS)

    def analyze_single_product(self, product: ProductRecord) -> QualityReport:
        report = self.supervisor.run(product, self.batch)
        quality_dimensions = report["quality_dimensions"]
        overall_score = int(round(sum(quality_dimensions.values()) / max(len(quality_dimensions), 1)))
        issues = report["issues"]
        corrections = report["proposed_corrections"]
        requires_human_review = bool(report["requires_human_review"])
        return QualityReport(
            product_id=product.sku,
            overall_quality_score=overall_score,
            quality_dimensions={k: int(v) for k, v in quality_dimensions.items()},
            issues=issues,
            proposed_corrections=corrections,
            confidence=float(report["confidence"]),
            requires_human_review=requires_human_review,
            decision=report["decision"],
            investigation_summary=report["investigation_summary"],
            evidence=report["evidence"],
        )

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
        with open(file_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        return file_path
