from __future__ import annotations

from time import perf_counter
from typing import Any, Dict, Optional, Sequence

from ..demo_data import POLICY_DOCS
from ..models import Issue, PolicyCitation, ProductRecord
from ..observability import record_rag_retrieval, trace_span
from .attribute_validation import ProductAttributeValidationAgent
from .correction import ProductCorrectionAgent
from .duplicate_resolution import DuplicateEntityResolutionAgent
from .human_review import HumanReviewAgent
from .investigation import ProductQualityInvestigationAgent
from .policy_rag import ProductPolicyRAGAgent
from .profiling import ProductDataProfilingAgent
from .taxonomy import ProductTaxonomyAgent
from .validation import ProductQualityValidationAgent


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
        with trace_span(
            "Supervisor",
            agent_name="supervisor",
            product_id=product.sku,
            sku=product.sku,
            input_summary={"batch_size": len(product_batch)},
        ) as supervisor_span:
            with trace_span("Product Data Profiling", agent_name="product_data_profiling", product_id=product.sku):
                profiling = self.profiling_agent.run(product)
            with trace_span("Taxonomy Validation", agent_name="taxonomy", product_id=product.sku):
                taxonomy = self.taxonomy_agent.run(product)
            with trace_span("Attribute Validation", agent_name="attribute_validation", product_id=product.sku):
                attributes = self.attribute_agent.run(product)
            with trace_span("Duplicate Resolution", agent_name="duplicate_resolution", product_id=product.sku):
                duplicates = self.duplicate_agent.run(product, product_batch)
            keyword_tokens = [
                product.category,
                product.brand,
                product.model,
                product.color or "",
                product.storage or "",
                product.title,
            ]
            retrieval_started = perf_counter()
            with trace_span("Product Policy Retrieval", agent_name="product_policy_rag", product_id=product.sku):
                policies = self.policy_agent.retrieve(keyword_tokens)
            record_rag_retrieval(
                len(policies),
                (perf_counter() - retrieval_started) * 1000,
                bool(policies),
            )
            with trace_span("Product Quality Investigation", agent_name="investigation", product_id=product.sku):
                investigation = self.investigation_agent.run(
                    product, profiling, taxonomy, attributes, duplicates, policies
                )
            with trace_span("Correction Generation", agent_name="correction", product_id=product.sku):
                corrections = self.correction_agent.run(product, investigation, policies)
            with trace_span("Quality Validation", agent_name="quality_validation", product_id=product.sku):
                validation = self.validation_agent.run(product, corrections)

            if validation in {"HUMAN_REVIEW", "BLOCK"} or investigation["recommended_correction_mode"] == "HUMAN_REVIEW":
                with trace_span("Human Review Routing", agent_name="human_review", product_id=product.sku):
                    human_route = self.human_agent.run(product, corrections, investigation)
                decision = "HUMAN_REVIEW"
                requires_human = True
                summary = "High-risk or insufficiently supported correction requires human review."
            else:
                human_route = {}
                decision = validation if validation in {"PASS", "RETRY"} else investigation["recommended_correction_mode"]
                requires_human = False
                summary = investigation["root_cause_hypothesis"]

            result = {
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
            supervisor_span["summary"] = {
                "issue_count": len(result["issues"]),
                "correction_count": len(result["proposed_corrections"]),
                "decision": decision,
            }
            return result

    def _compute_quality_dimensions(
        self,
        profiling: Sequence[Issue],
        taxonomy: Sequence[Issue],
        attributes: Sequence[Issue],
        duplicates: Sequence[Issue],
    ) -> Dict[str, int]:
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
