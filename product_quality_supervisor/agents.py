from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .demo_data import CATEGORY_RULES, POLICY_DOCS, canonical_brand, normalize_color, normalize_storage
from .models import Correction, Issue, PolicyCitation, ProductRecord


class ToolResult:
    def __init__(self, tool_name: str, payload: Dict[str, Any]):
        self.tool_name = tool_name
        self.payload = payload


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


class ProductPolicyRAGAgent:
    def __init__(self, docs: Optional[Sequence[PolicyCitation]] = None):
        self.docs = list(docs or POLICY_DOCS)

    def retrieve(self, keywords: Sequence[str]) -> List[PolicyCitation]:
        keyword_set = {k.lower() for k in keywords if k}
        results: List[PolicyCitation] = []
        for doc in self.docs:
            text = f"{doc.title} {doc.section} {doc.citation}".lower()
            if keyword_set and any(keyword in text for keyword in keyword_set):
                results.append(doc)
        return results or list(self.docs)


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


class ProductCorrectionAgent:
    def run(self, product: ProductRecord, investigation: Dict[str, Any], policies: Sequence[PolicyCitation]) -> List[Correction]:
        corrections: List[Correction] = []
        title = product.title or ""
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


class HumanReviewAgent:
    def run(self, product: ProductRecord, corrections: Sequence[Correction], investigation: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "decision": "HUMAN_REVIEW",
            "route": "product_data_analyst_queue",
            "product": product.to_dict(),
            "corrections": [item.to_dict() for item in corrections],
            "summary": investigation.get("root_cause_hypothesis", "needs review"),
        }


class SupervisorAgent:
    def __init__(self, policy_docs: Optional[Sequence[PolicyCitation]] = None):
        self.policy_agent = ProductPolicyRAGAgent(policy_docs or POLICY_DOCS)
        self.profiling_agent = ProductDataProfilingAgent()
        self.taxonomy_agent = ProductTaxonomyAgent()
        self.attribute_agent = ProductAttributeValidationAgent()
        self.duplicate_agent = DuplicateEntityResolutionAgent()
        self.investigation_agent = ProductQualityInvestigationAgent()
        self.correction_agent = ProductCorrectionAgent()
        self.validation_agent = ProductQualityValidationAgent()
        self.human_agent = HumanReviewAgent()

    def run(self, product: ProductRecord, product_batch: Sequence[ProductRecord]) -> Dict[str, Any]:
        profiling = self.profiling_agent.run(product)
        taxonomy = self.taxonomy_agent.run(product)
        attributes = self.attribute_agent.run(product)
        duplicates = self.duplicate_agent.run(product, product_batch)
        keyword_tokens = [product.category, product.brand, product.model, product.color or "", product.storage or "", product.title]
        policies = self.policy_agent.retrieve(keyword_tokens)
        investigation = self.investigation_agent.run(product, profiling, taxonomy, attributes, duplicates, policies)
        corrections = self.correction_agent.run(product, investigation, policies)
        validation = self.validation_agent.run(product, corrections)

        if validation in {"HUMAN_REVIEW", "BLOCK"} or investigation["recommended_correction_mode"] == "HUMAN_REVIEW":
            human_route = self.human_agent.run(product, corrections, investigation)
            decision = "HUMAN_REVIEW"
            requires_human = True
            summary = "High-risk or insufficiently supported correction requires human review."
        else:
            human_route = {}
            decision = validation if validation in {"PASS", "RETRY"} else investigation["recommended_correction_mode"]
            requires_human = False
            summary = investigation["root_cause_hypothesis"]

        report = {
            "product_id": product.sku,
            "quality_dimensions": self._compute_quality_dimensions(profiling, taxonomy, attributes, duplicates),
            "issues": [issue.to_dict() for issue in profiling + taxonomy + attributes + duplicates],
            "proposed_corrections": [correction.to_dict() for correction in corrections],
            "confidence": investigation["confidence"],
            "requires_human_review": requires_human,
            "decision": decision,
            "investigation_summary": summary,
            "evidence": investigation["relevant_policy"],
            "human_review": human_route,
        }
        return report

    def _compute_quality_dimensions(self, profiling: Sequence[Issue], taxonomy: Sequence[Issue], attributes: Sequence[Issue], duplicates: Sequence[Issue]) -> Dict[str, int]:
        all_issues = list(profiling) + list(taxonomy) + list(attributes) + list(duplicates)
        severity_weight = {"high": 25, "medium": 12, "low": 5}
        score_penalty = sum(severity_weight.get(issue.severity, 5) for issue in all_issues)
        quality = max(0, 100 - score_penalty)

        completeness = max(0, 100 - 10 * sum(1 for issue in all_issues if issue.issue_type in {"missing_value", "missing_category_attribute"}))
        accuracy = max(0, 100 - 12 * sum(1 for issue in all_issues if issue.issue_type in {"attribute_validation", "schema_violation"}))
        consistency = max(0, 100 - 15 * sum(1 for issue in all_issues if issue.issue_type in {"duplicate", "taxonomy", "color_format_inconsistency"}))
        validity = max(0, 100 - 14 * sum(1 for issue in all_issues if issue.issue_type in {"schema_violation", "invalid_range", "invalid_price_range"}))
        uniqueness = 100 if not any(issue.issue_type == "duplicate" for issue in all_issues) else 60
        taxonomy_score = max(0, 100 - 20 * sum(1 for issue in all_issues if issue.issue_type in {"taxonomy", "incorrect_category"}))

        return {
            "completeness": completeness,
            "accuracy": accuracy,
            "consistency": consistency,
            "validity": validity,
            "uniqueness": uniqueness,
            "taxonomy": taxonomy_score,
            "overall": quality,
        }
