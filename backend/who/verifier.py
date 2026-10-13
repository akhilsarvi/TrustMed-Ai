from __future__ import annotations


def verify_claim(claim: str, evidence: list[dict]) -> dict:
    if not claim:
        return {
            "status": "WHO SOURCE NOT FOUND",
            "summary": "No claim provided.",
            "source": "",
            "url": "",
        }

    claim_l = (claim or "").lower()
    matched = []
    for item in evidence:
        text = (item.get("excerpt") or "").lower()
        if claim_l in text or any(word in text for word in claim_l.split()[:3]):
            matched.append(item)

    if not matched:
        return {
            "status": "WHO SOURCE NOT FOUND",
            "summary": "No relevant WHO source was found for this claim.",
            "source": "",
            "url": "",
        }

    best = matched[0]
    text = (best.get("excerpt") or "").lower()
    if "contradict" in text or "not recommended" in text and any(k in claim_l for k in ["disease", "infection", "medication", "treatment"]):
        status = "CONTRADICTED / INCONSISTENT"
    elif "not enough evidence" in text or "some evidence" in text or "may" in text:
        status = "PARTIALLY SUPPORTED"
    else:
        status = "SUPPORTED BY WHO"

    return {
        "status": status,
        "summary": best.get("excerpt", "")[:400],
        "source": best.get("title", "WHO page"),
        "url": best.get("url", ""),
    }
