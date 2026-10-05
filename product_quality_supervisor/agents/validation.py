from __future__ import annotations

from typing import Sequence

from ..models import Correction, ProductRecord


class ProductQualityValidationAgent:
    def run(self, product: ProductRecord, corrections: Sequence[Correction]) -> str:
        if not corrections:
            return "PASS"
        for correction in corrections:
            evidence_supported = bool(correction.evidence)
            if not evidence_supported:
                return "BLOCK"
            if correction.requires_human_review:
                return "HUMAN_REVIEW"
            if correction.mode == "AUTO_FIX":
                return "PASS"
        return "RETRY"
