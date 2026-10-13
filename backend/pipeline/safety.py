from __future__ import annotations

from collections import Counter
from typing import Any


def assess_evidence(evidence: list[dict[str, Any]], minimum: int = 2) -> dict[str, Any]:
    scores = [float(item.get("trust_score", 0)) for item in evidence]
    trusted = [score for score in scores if score > 0]
    sufficient = len(trusted) >= minimum
    average = round(sum(trusted) / len(trusted), 2) if trusted else 0.0
    return {
        "sufficient": sufficient,
        "evidence_count": len(evidence),
        "trusted_evidence_count": len(trusted),
        "average_trust_score": average,
        "status": "SUFFICIENT" if sufficient else "INSUFFICIENT_EVIDENCE",
        "message": (
            "Evidence is available for a grounded response."
            if sufficient
            else "Evidence is insufficient for a reliable recommendation; seek clinician review."
        ),
    }


def detect_contradictions(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Surface simple answer-level conflicts without silently resolving them."""
    statements = []
    for item in evidence:
        text = (item.get("text") or "").lower()
        question = item.get("question", "")
        if not text:
            continue
        stance = None
        if "antibiotics don't" in text or "antibiotics cannot" in text or "not effective" in text:
            stance = "against_antibiotics"
        elif "treated with antibiotics" in text or "antibiotics are" in text:
            stance = "supports_antibiotics"
        if stance:
            statements.append({"stance": stance, "question": question, "text": item.get("text", "")})

    stances = Counter(item["stance"] for item in statements)
    if len(stances) < 2:
        return []
    return [{
        "topic": "antibiotic treatment",
        "status": "CONFLICTING_EVIDENCE",
        "message": "Retrieved sources express different positions; a clinician should resolve the context.",
        "sources": statements,
    }]
