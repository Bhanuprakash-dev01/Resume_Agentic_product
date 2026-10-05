from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Sequence

from ..models import Issue, PolicyCitation, ProductRecord


class ProductQualityInvestigationAgent:
    def run(
        self,
        product: ProductRecord,
        profiling: Sequence[Issue],
        taxonomy: Sequence[Issue],
        attributes: Sequence[Issue],
        duplicates: Sequence[Issue],
        policies: Sequence[PolicyCitation],
    ) -> Dict[str, Any]:
        combined = list(profiling) + list(taxonomy) + list(attributes) + list(duplicates)
        issue_map: Dict[str, List[Issue]] = defaultdict(list)
        for issue in combined:
            issue_map[issue.field].append(issue)

        severity_scores = {"high": 3, "medium": 2, "low": 1}
        total_severity = sum(severity_scores.get(issue.severity, 1) * issue.confidence for issue in combined)
        major_rank = max((issue.confidence for issue in combined), default=0.0)

        root_cause = "data-quality drift and inconsistent catalog normalization" if combined else "no material issue detected"
        if any(issue.issue_type == "taxonomy" or issue.name == "incorrect_category" for issue in combined):
            root_cause = "taxonomy misclassification combined with incomplete normalization"
        elif any(issue.issue_type == "duplicate" for issue in combined):
            root_cause = "duplicate and near-duplicate record clustering"

        recommended = "AUTO_FIX" if major_rank >= 0.8 and len(combined) <= 5 else "SUGGEST_FIX"
        if any(issue.severity == "high" and issue.confidence >= 0.9 for issue in combined):
            recommended = "HUMAN_REVIEW"

        return {
            "issue_type": "multi_agent_review" if combined else "clean",
            "affected_fields": sorted(issue_map.keys()),
            "root_cause_hypothesis": root_cause,
            "severity": "high" if total_severity >= 8 else "medium" if total_severity >= 4 else "low",
            "supporting_evidence": [issue.to_dict() for issue in combined],
            "recommended_correction_mode": recommended,
            "relevant_policy": [policy.to_dict() for policy in policies[:3]],
            "confidence": min(0.99, max(0.5, major_rank)),
        }
