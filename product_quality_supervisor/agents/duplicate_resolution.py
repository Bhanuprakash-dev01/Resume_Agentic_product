from __future__ import annotations

import re
from typing import List, Sequence

from ..models import Issue, ProductRecord


class DuplicateEntityResolutionAgent:
    def run(self, product: ProductRecord, product_batch: Sequence[ProductRecord]) -> List[Issue]:
        findings: List[Issue] = []
        for candidate in product_batch:
            if candidate.sku == product.sku:
                continue
            if candidate.gtin and product.gtin and candidate.gtin == product.gtin:
                findings.append(Issue("duplicate_gtin", "gtin", "duplicate", "high", f"Matched GTIN with {candidate.sku}.", 0.97, "group_duplicate_review"))
                continue
            title_a = re.sub(r"[^a-z0-9]+", " ", (product.title or "").lower())
            title_b = re.sub(r"[^a-z0-9]+", " ", (candidate.title or "").lower())
            title_similarity = 1.0 if title_a == title_b else 0.0
            brand_match = (product.brand or "").lower() == (candidate.brand or "").lower()
            model_match = (product.model or "").lower() in (candidate.model or "").lower() or (candidate.model or "").lower() in (product.model or "").lower()
            if brand_match and model_match and title_similarity >= 0.6:
                findings.append(Issue("near_duplicate_title", "title", "duplicate", "medium", f"Likely duplicate with {candidate.sku}; strong model and title overlap.", 0.92, "review_duplicate_group"))
        return findings
