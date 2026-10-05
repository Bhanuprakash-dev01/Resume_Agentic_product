from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from ..demo_data import canonical_brand, normalize_color, normalize_storage
from ..models import Correction, PolicyCitation, ProductRecord


class ProductCorrectionAgent:
    def run(self, product: ProductRecord, investigation: Dict[str, Any], policies: Sequence[PolicyCitation]) -> List[Correction]:
        corrections: List[Correction] = []
        brand = product.brand or ""
        normalized_brand = canonical_brand(str(brand))

        if brand and normalized_brand != str(brand).strip() and "brand" in investigation["affected_fields"]:
            corrections.append(
                Correction(
                    field="brand",
                    original_value=product.brand,
                    proposed_value=normalized_brand,
                    mode="AUTO_FIX" if normalized_brand.lower() in {"apple", "samsung", "google"} else "SUGGEST_FIX",
                    rationale="Normalize brand names to the canonical catalog name.",
                    evidence=[policy.to_dict() for policy in policies[:2]],
                    confidence=0.91,
                )
            )

        if product.color is not None and str(product.color).lower() in {"blk", "black"}:
            color = normalize_color(str(product.color))
            if color != str(product.color).title():
                corrections.append(
                    Correction(
                        field="color",
                        original_value=product.color,
                        proposed_value=color,
                        mode="AUTO_FIX",
                        rationale="Normalize the color attribute to a catalog-standard value.",
                        evidence=[policy.to_dict() for policy in policies if "Color" in policy.title],
                        confidence=0.87,
                    )
                )

        if product.storage is not None:
            normalized_storage = normalize_storage(str(product.storage))
            if normalized_storage and normalized_storage != str(product.storage).strip():
                corrections.append(
                    Correction(
                        field="storage",
                        original_value=product.storage,
                        proposed_value=normalized_storage,
                        mode="AUTO_FIX",
                        rationale="Normalize storage units to canonical unit format.",
                        evidence=[policy.to_dict() for policy in policies if "Naming" in policy.title or "attributes" in policy.title.lower()],
                        confidence=0.9,
                    )
                )

        if product.title and "iphone" in product.title.lower() and product.category not in {"smartphones"}:
            corrections.append(
                Correction(
                    field="category",
                    original_value=product.category,
                    proposed_value="smartphones",
                    mode="SUGGEST_FIX",
                    rationale="The title indicates a smartphone but category assignment is inconsistent with taxonomy.",
                    evidence=[policy.to_dict() for policy in policies if "Taxonomy" in policy.title],
                    confidence=0.92,
                    requires_human_review=True,
                )
            )

        if not corrections and product.title and "blk" in product.title.lower():
            corrections.append(
                Correction(
                    field="title",
                    original_value=product.title,
                    proposed_value=re.sub(r"\bblk\b", "Black", product.title, flags=re.IGNORECASE),
                    mode="SUGGEST_FIX",
                    rationale="Improve title normalization when a non-standard shorthand is detected.",
                    evidence=[policy.to_dict() for policy in policies if "Naming" in policy.title],
                    confidence=0.6,
                    requires_human_review=True,
                )
            )

        return corrections
