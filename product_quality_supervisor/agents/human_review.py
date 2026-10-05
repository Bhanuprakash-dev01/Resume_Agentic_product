from __future__ import annotations

from typing import Any, Dict, Sequence

from ..models import Correction, ProductRecord


class HumanReviewAgent:
    def run(self, product: ProductRecord, corrections: Sequence[Correction], investigation: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "decision": "HUMAN_REVIEW",
            "route": "product_data_analyst_queue",
            "product": product.to_dict(),
            "corrections": [item.to_dict() for item in corrections],
            "summary": investigation.get("root_cause_hypothesis", "needs review"),
        }
