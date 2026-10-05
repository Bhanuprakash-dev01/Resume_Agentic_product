from __future__ import annotations

from typing import List

from ..demo_data import CATEGORY_RULES
from ..models import Issue, ProductRecord


class ProductDataProfilingAgent:
    def run(self, product: ProductRecord) -> List[Issue]:
        findings: List[Issue] = []
        required = ["sku", "title", "category", "brand", "price"]
        for field in required:
            value = getattr(product, field, None)
            if value in (None, ""):
                findings.append(Issue("missing_required_field", field, "missing_value", "high", f"{field} is empty or missing.", 0.95, "complete_required_fields"))

        if product.category in CATEGORY_RULES:
            for required_field in CATEGORY_RULES[product.category]["required_fields"]:
                value = getattr(product, required_field, None)
                if value in (None, ""):
                    findings.append(Issue("missing_category_attribute", required_field, "missing_value", "high", f"{required_field} is mandatory for {product.category}.", 0.93, "collect_missing_attribute"))

        if product.price is not None:
            try:
                numeric_price = float(product.price)
                if numeric_price < 0 or numeric_price > 100000:
                    findings.append(Issue("invalid_price_range", "price", "invalid_range", "high", f"Price {product.price} is outside a realistic range.", 0.88, "validate_price"))
            except (TypeError, ValueError):
                findings.append(Issue("price_not_numeric", "price", "schema_violation", "high", f"Price '{product.price}' cannot be parsed as a number.", 0.96, "normalize_numeric_field"))

        if product.color is not None and str(product.color).strip() == "":
            findings.append(Issue("empty_color", "color", "missing_value", "medium", "Color field is empty string.", 0.89, "populate_color"))

        if product.storage is not None and str(product.storage).strip() == "":
            findings.append(Issue("empty_storage", "storage", "missing_value", "medium", "Storage field is empty string.", 0.82, "normalize_storage"))

        return findings
