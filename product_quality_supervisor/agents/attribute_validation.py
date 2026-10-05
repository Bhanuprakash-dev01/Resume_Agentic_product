from __future__ import annotations

from typing import List

from ..demo_data import normalize_color, normalize_storage
from ..models import Issue, ProductRecord


class ProductAttributeValidationAgent:
    def run(self, product: ProductRecord) -> List[Issue]:
        findings: List[Issue] = []

        if product.brand and product.brand.lower() not in {"apple", "samsung", "google", "dell", "lenovo", "asus", "whirlpool", "lg", "philips", "nike", "adidas", "puma"}:
            findings.append(Issue("brand_variation", "brand", "attribute_validation", "medium", f"Brand '{product.brand}' is non-standard or inconsistent.", 0.85, "normalize_brand"))

        if product.color is not None:
            normalized = normalize_color(str(product.color))
            if normalized != str(product.color).title() and str(product.color).strip() != "":
                findings.append(Issue("color_format_inconsistency", "color", "attribute_validation", "medium", f"Color '{product.color}' should be normalized to '{normalized}'.", 0.8, "normalize_color"))

        if product.storage is not None:
            normalized = normalize_storage(str(product.storage))
            if normalized and normalized != str(product.storage).strip():
                findings.append(Issue("storage_unit_inconsistency", "storage", "attribute_validation", "medium", f"Storage '{product.storage}' should follow '{normalized}' formatting.", 0.82, "format_storage_unit"))

        if product.price is not None:
            try:
                value = float(product.price)
                if value > 10000 and product.category in {"shoes", "home_appliances"}:
                    findings.append(Issue("price_outlier", "price", "attribute_validation", "high", f"Price {product.price} is suspicious for {product.category}.", 0.74, "review_pricing"))
            except (TypeError, ValueError):
                findings.append(Issue("price_invalid_format", "price", "schema_violation", "high", f"Price '{product.price}' is not a valid numeric value.", 0.96, "correct_numeric_field"))

        return findings
