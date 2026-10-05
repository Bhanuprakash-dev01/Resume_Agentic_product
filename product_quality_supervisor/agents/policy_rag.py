from __future__ import annotations

from typing import List, Optional, Sequence

from ..demo_data import POLICY_DOCS
from ..models import PolicyCitation


class ProductPolicyRAGAgent:
    def __init__(self, docs: Optional[Sequence[PolicyCitation]] = None):
        self.docs = list(docs or POLICY_DOCS)

    def retrieve(self, keywords: Sequence[str]) -> List[PolicyCitation]:
        keyword_set = {keyword.lower() for keyword in keywords if keyword}
        results: List[PolicyCitation] = []
        for doc in self.docs:
            text = f"{doc.title} {doc.section} {doc.citation}".lower()
            if keyword_set and any(keyword in text for keyword in keyword_set):
                results.append(doc)
        return results or list(self.docs)
