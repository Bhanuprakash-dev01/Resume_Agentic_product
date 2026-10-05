from typing import Any, Dict

from .attribute_validation import ProductAttributeValidationAgent
from .correction import ProductCorrectionAgent
from .duplicate_resolution import DuplicateEntityResolutionAgent
from .human_review import HumanReviewAgent
from .investigation import ProductQualityInvestigationAgent
from .policy_rag import ProductPolicyRAGAgent
from .profiling import ProductDataProfilingAgent
from .supervisor import SupervisorAgent
from .taxonomy import ProductTaxonomyAgent
from .validation import ProductQualityValidationAgent


class ToolResult:
    def __init__(self, tool_name: str, payload: Dict[str, Any]):
        self.tool_name = tool_name
        self.payload = payload


__all__ = [
    "DuplicateEntityResolutionAgent",
    "HumanReviewAgent",
    "ProductAttributeValidationAgent",
    "ProductCorrectionAgent",
    "ProductDataProfilingAgent",
    "ProductPolicyRAGAgent",
    "ProductQualityInvestigationAgent",
    "ProductQualityValidationAgent",
    "ProductTaxonomyAgent",
    "SupervisorAgent",
    "ToolResult",
]
