from __future__ import annotations

from typing import Any


GENERAL_QUESTIONS = [
    "When did the symptoms start, and are they getting better or worse?",
    "How severe are the symptoms from 0 to 10?",
    "Have you measured your temperature or noticed any breathing difficulty?",
    "Have you taken any medicine for these symptoms, and did it help?",
]

DISEASE_QUESTIONS = {
    "pneumonia": [
        "Do you have shortness of breath, chest pain, chills, or cough with phlegm?",
        "How high has your fever been, and for how many days?",
        "Have you had a chest X-ray, oxygen reading, or recent respiratory infection?",
    ],
    "tuberculosis": [
        "Have you had a cough lasting more than two weeks, night sweats, weight loss, or blood in sputum?",
        "Have you had close contact with anyone diagnosed with tuberculosis?",
        "Have you had a TB test or chest imaging?",
    ],
    "common cold": [
        "Do you also have a runny or blocked nose, sneezing, or sore throat?",
        "How long have the symptoms lasted?",
        "Do you have shortness of breath, chest pain, or a high persistent fever?",
    ],
}


def validate_candidates(symptoms: list[str], diseases: list[dict[str, Any]]) -> dict[str, Any]:
    clean_symptoms = [str(item).strip().lower() for item in symptoms if str(item).strip()]
    top = diseases[0] if diseases else None
    match_count = int(top.get("match_count", 0)) if top else 0
    total_symptoms = int(top.get("total_symptoms", 0)) if top else 0
    score = float(top.get("score", 0.0)) if top else 0.0

    # This is a triage threshold, not a clinical diagnosis threshold.
    validated = bool(top and len(clean_symptoms) >= 3 and match_count >= 2 and score > 0)
    disease = top.get("disease") if top else None
    questions = DISEASE_QUESTIONS.get(str(disease).lower(), GENERAL_QUESTIONS) if disease else GENERAL_QUESTIONS
    if len(clean_symptoms) < 3:
        questions = GENERAL_QUESTIONS[:]

    candidates = []
    for item in diseases[:3]:
        coverage = round(
            int(item.get("match_count", 0)) / max(int(item.get("total_symptoms", 0)), 1),
            3,
        )
        candidates.append({
            "disease": item.get("disease"),
            "match_count": item.get("match_count", 0),
            "score": item.get("score", 0.0),
            "symptom_coverage": coverage,
            "confidence": "provisional" if not validated else "supported",
        })

    return {
        "validated": validated,
        "status": "SUPPORTED_CANDIDATE" if validated else "NEEDS_MORE_INFORMATION",
        "most_likely_disease": disease,
        "candidates": candidates,
        "questions": questions,
        "reason": (
            "The leading candidate has enough symptom overlap for an evidence-grounded explanation."
            if validated
            else "The available symptoms do not safely distinguish the possible conditions yet."
        ),
        "matched_symptoms": match_count,
        "provided_symptoms": len(clean_symptoms),
        "candidate_total_symptoms": total_symptoms,
        "score": score,
    }
