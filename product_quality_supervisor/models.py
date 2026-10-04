from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PolicyCitation:
    title: str
    source: str
    citation: str
    section: str = "n/a"

    def to_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "source": self.source,
            "citation": self.citation,
            "section": self.section,
        }


@dataclass
class Issue:
    name: str
    field: str
    issue_type: str
    severity: str
    evidence: str
    confidence: float
    recommended_action: str = "investigate"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "field": self.field,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 3),
            "recommended_action": self.recommended_action,
        }


@dataclass
class Correction:
    field: str
    original_value: Any
    proposed_value: Any
    mode: str
    rationale: str
    evidence: List[Dict[str, Any]]
    confidence: float
    requires_human_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "original_value": self.original_value,
            "proposed_value": self.proposed_value,
            "mode": self.mode,
            "rationale": self.rationale,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 3),
            "requires_human_review": self.requires_human_review,
        }


@dataclass
class ProductRecord:
    sku: str
    title: str
    category: str
    brand: str
    color: Optional[str] = None
    storage: Optional[str] = None
    price: Any = None
    weight: Optional[str] = None
    dimensions: Optional[str] = None
    description: str = ""
    gtin: Optional[str] = None
    model: Optional[str] = None
    source: str = "demo"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sku": self.sku,
            "title": self.title,
            "category": self.category,
            "brand": self.brand,
            "color": self.color,
            "storage": self.storage,
            "price": self.price,
            "weight": self.weight,
            "dimensions": self.dimensions,
            "description": self.description,
            "gtin": self.gtin,
            "model": self.model,
            "source": self.source,
            "metadata": self.metadata,
        }


@dataclass
class QualityReport:
    product_id: str
    overall_quality_score: int
    quality_dimensions: Dict[str, int]
    issues: List[Dict[str, Any]]
    proposed_corrections: List[Dict[str, Any]]
    confidence: float
    requires_human_review: bool
    decision: str
    investigation_summary: str
    evidence: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "overall_quality_score": self.overall_quality_score,
            "quality_dimensions": self.quality_dimensions,
            "issues": self.issues,
            "proposed_corrections": self.proposed_corrections,
            "confidence": round(self.confidence, 3),
            "requires_human_review": self.requires_human_review,
            "decision": self.decision,
            "investigation_summary": self.investigation_summary,
            "evidence": self.evidence,
        }


@dataclass
class WorkflowState:
    product_id: str
    phase: str = "queued"
    findings: List[Issue] = field(default_factory=list)
    policies: List[PolicyCitation] = field(default_factory=list)
    corrections: List[Correction] = field(default_factory=list)
    validation: str = "pending"
    routed_to_human: bool = False
    summary: str = ""
