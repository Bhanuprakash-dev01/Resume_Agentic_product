from __future__ import annotations

from typing import List

from ..demo_data import CATEGORY_RULES
from ..models import Issue, ProductRecord


class ProductTaxonomyAgent:
    def run(self, product: ProductRecord) -> List[Issue]:
        findings: List[Issue] = []
        canonical = product.category.lower()
        category_mapping = {
            "computer accessories": "smartphones",
            "accessories": "smartphones",
            "phone": "smartphones",
            "mobile phone": "smartphones",
            "smart_phone": "smartphones",
            "smartphone": "smartphones",
            "laptop": "laptops",
            "notebook": "laptops",
            "shirt": "shoes",
            "shoe": "shoes",
        }
        expected = category_mapping.get(canonical, canonical)
        if product.category not in CATEGORY_RULES and expected in CATEGORY_RULES:
            findings.append(Issue("taxonomy_mismatch", "category", "taxonomy", "high", f"Category '{product.category}' is not a valid taxonomy leaf and resembles '{expected}'.", 0.9, "recommend_canonical_category"))

        if product.category not in CATEGORY_RULES and product.title.lower().find("iphone") >= 0:
            findings.append(Issue("incorrect_category", "category", "taxonomy", "high", "Product title indicates a smartphone but category is not recognized.", 0.92, "route_to_taxonomy_recommendation"))

        return findings
