import re

CANONICAL_ENTITIES = {
    "hepatitis a": ("Hepatitis A", "DISEASE"),
    "hepatitis-a": ("Hepatitis A", "DISEASE"),
    "hepatitis a infection": ("Hepatitis A", "DISEASE"),
    "autoimmune hepatitis": ("Autoimmune Hepatitis", "DISEASE"),
    "hepatitis b": ("Hepatitis B", "DISEASE"),
    "hepatitis c": ("Hepatitis C", "DISEASE"),
    "osteoarthritis": ("Osteoarthritis", "DISEASE"),
    "rheumatic fever": ("Rheumatic Fever", "DISEASE"),
    "pneumonia": ("Pneumonia", "DISEASE"),
    "gerd": ("GERD", "DISEASE"),
    "gastroesophageal reflux disease": ("GERD", "DISEASE"),
    "fever": ("Fever", "SYMPTOM"),
    "pyrexia": ("Fever", "SYMPTOM"),
    "high temperature": ("Fever", "SYMPTOM"),
    "jaundice": ("Jaundice", "SYMPTOM"),
    "yellowing of eyes": ("Jaundice", "SYMPTOM"),
    "fatigue": ("Fatigue", "SYMPTOM"),
    "joint pain": ("Joint Pain", "SYMPTOM"),
    "supportive care": ("Supportive Care", "TREATMENT"),
    "paracetamol": ("Paracetamol", "MEDICATION"),
    "acetaminophen": ("Paracetamol", "MEDICATION"),
}


def normalize_clinical_entity(raw_entity: str, raw_type: str = "") -> tuple[str, str]:
    """
    Normalizes a clinical entity name and entity type to standard canonical representations.
    """
    clean = str(raw_entity or "").strip().lower()
    if clean in CANONICAL_ENTITIES:
        return CANONICAL_ENTITIES[clean]
    
    # Capitalize cleanly if unknown
    norm_name = str(raw_entity or "").strip().title()
    norm_type = (raw_type or "DISEASE").upper()
    if norm_type not in ["DISEASE", "SYMPTOM", "TREATMENT", "MEDICATION", "DIAGNOSTIC_TEST", "CONDITION", "PROCEDURE"]:
        norm_type = "DISEASE"
    return norm_name, norm_type


class ClinicalRelevanceFilter:
    """
    Dedicated Clinical Relevance Filter for TrustMed AI.
    Distinguishes between semantically similar text and clinically relevant evidence.
    Generates explicit clinical_relevance_reason explanations.
    """

    def __init__(self):
        self.treatment_keywords = {
            "treat", "treatment", "therapy", "drug", "antibiotic",
            "medication", "prescribed", "care", "management", "dose"
        }
        self.diagnostic_keywords = {
            "diagnose", "diagnosis", "test", "symptom", "manifestation", "clinical"
        }

    def evaluate_item(self, candidate_disease: str, symptoms: list, item: dict) -> dict:
        text = (item.get("text", "") or "").lower()
        question = (item.get("question", "") or "").lower()
        combined = f"{question} {text}"
        
        norm_entity, entity_type = normalize_clinical_entity(candidate_disease)
        dis_lower = norm_entity.lower()

        # 1. Entity Mismatch Detection
        entity_mismatch = False
        mismatch_reason = ""

        if dis_lower:
            if "hepatitis a" in dis_lower and ("autoimmune hepatitis" in combined or "hepatitis b" in combined or "hepatitis c" in combined):
                entity_mismatch = True
                mismatch_reason = f"Evidence specifies a different etiology (Autoimmune/B/C) than target '{norm_entity}'."
            elif "osteoarthritis" in dis_lower and ("rheumatic fever" in combined or "rheumatoid arthritis" in combined):
                entity_mismatch = True
                mismatch_reason = f"Evidence specifies a different condition (Rheumatic/Rheumatoid) than target '{norm_entity}'."
            elif "gerd" in dis_lower and "cardiac chest pain" in combined:
                entity_mismatch = True
                mismatch_reason = f"Evidence specifies cardiac etiology rather than target '{norm_entity}'."

        # 2. Disease Matching Score
        disease_match = False
        dis_tokens = set(re.findall(r"[a-z0-9]+", dis_lower)) - {"disease", "infection", "syndrome", "fever", "pain"}
        if dis_lower and (dis_lower in combined or (dis_tokens and len(dis_tokens & set(re.findall(r"[a-z0-9]+", combined))) == len(dis_tokens))):
            disease_match = True

        # 3. Symptom Relevance
        symptom_hits = 0
        for s in symptoms:
            s_clean = str(s).lower().strip()
            if s_clean and s_clean in combined:
                symptom_hits += 1
        symptom_relevance = (symptom_hits > 0) or disease_match

        # 4. Treatment & Clinical Relevance
        text_tokens = set(re.findall(r"[a-z0-9]+", combined))
        treatment_match = bool(text_tokens & self.treatment_keywords)

        # 5. Determine Relationship Category & Explicit Reasoning
        if disease_match and not entity_mismatch:
            category = "PRIMARY_SUPPORTING"
            relevance_score = 96.0
            relevance_reason = f"Evidence content directly matches normalized target entity '{norm_entity}' ({entity_type})."
        elif entity_mismatch:
            category = "RELATED_ENTITY"
            relevance_score = 35.0
            relevance_reason = mismatch_reason
        elif symptom_relevance:
            category = "PRIMARY_SUPPORTING"
            relevance_score = 75.0
            relevance_reason = f"Evidence discusses clinical symptoms/manifestations related to '{norm_entity}'."
        else:
            category = "CLINICALLY_IRRELEVANT"
            relevance_score = 20.0
            relevance_reason = f"Target entity '{norm_entity}' could not be matched to the evidence content."

        return {
            "category": category,
            "relevance_score": relevance_score,
            "relevance_reason": relevance_reason,
            "normalized_entity": norm_entity,
            "entity_type": entity_type,
            "disease_match": disease_match,
            "entity_mismatch": entity_mismatch,
            "mismatch_reason": mismatch_reason,
            "symptom_relevance": symptom_relevance,
            "treatment_match": treatment_match,
        }

    def filter_evidences(self, candidate_disease: str, symptoms: list, evidences: list) -> dict:
        verified_evidence = []
        related_evidence = []

        for item in evidences:
            eval_res = self.evaluate_item(candidate_disease, symptoms, item)
            item_copy = dict(item)
            item_copy["clinical_filter"] = eval_res
            item_copy["disease_match"] = eval_res["disease_match"]
            item_copy["treatment_match"] = eval_res["treatment_match"]
            item_copy["clinical_relevance_reason"] = eval_res["relevance_reason"]

            if eval_res["category"] == "PRIMARY_SUPPORTING":
                verified_evidence.append(item_copy)
            elif eval_res["category"] == "RELATED_ENTITY":
                item_copy["relation_note"] = eval_res["mismatch_reason"] or "Related condition literature"
                related_evidence.append(item_copy)

        status = "OK"
        status_message = "Clinically relevant evidence filtered successfully."

        if not verified_evidence:
            if related_evidence:
                status = "RELATED_ONLY"
                status_message = "No direct evidence found for this candidate; showing related entity literature."
            else:
                status = "INSUFFICIENT"
                status_message = "Insufficient clinically relevant evidence."

        return {
            "verified_evidence": verified_evidence,
            "related_evidence": related_evidence,
            "status": status,
            "status_message": status_message,
        }

