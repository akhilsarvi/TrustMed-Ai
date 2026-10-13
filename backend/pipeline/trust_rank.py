import re
from config.settings import TRUSTRANK_WEIGHTS


class MedicalTrustRank:

    def __init__(self, weights=None):
        self.weights = weights or TRUSTRANK_WEIGHTS
        self.treatment_keywords = {
            "treat", "therapy", "drug", "antibiotic",
            "medication", "prescribed", "treatment", "care", "dose"
        }

    def score(self, query, disease, evidence):
        text = evidence.get("text", "").lower()
        question = evidence.get("question", "").lower()
        combined = f"{question} {text}"
        disease_lower = str(disease or "").lower().strip()

        filter_info = evidence.get("clinical_filter", {})
        
        # 1. Semantic Similarity (0 - 100)
        sim_val = min(1.0, float(evidence.get("score", 0.5))) * 100.0

        # 2. Clinical Relevance (0 - 100)
        rel_val = filter_info.get("relevance_score", 0.5) * 100.0
        if disease_lower and disease_lower in combined:
            rel_val = min(100.0, rel_val + 20.0)

        # 3. Source Reliability (0 - 100)
        source = str(evidence.get("source", "")).lower()
        if any(s in source for s in ["who", "cdc", "nih", "medlineplus", "pubmed"]):
            source_val = 100.0
        elif source:
            source_val = 80.0
        else:
            source_val = 60.0

        # 4. Knowledge Graph Consistency (0 - 100)
        kg_val = 100.0 if evidence.get("kg_verified", True) else 40.0

        # 5. Evidence Quality (0 - 100)
        tx_hits = sum(1 for k in self.treatment_keywords if k in combined)
        quality_val = min(100.0, 50.0 + tx_hits * 15.0)

        # Weighted composite score
        w = self.weights
        total_score = (
            w.get("semantic_similarity", 0.30) * sim_val +
            w.get("clinical_relevance", 0.30) * rel_val +
            w.get("source_reliability", 0.15) * source_val +
            w.get("kg_consistency", 0.15) * kg_val +
            w.get("evidence_quality", 0.10) * quality_val
        )

        final_score = round(max(0.0, min(100.0, total_score)), 1)
        return final_score

    def rank(self, query, disease, evidences):
        scored = []
        for e in evidences:
            filter_info = e.get("clinical_filter", {})
            if filter_info.get("category") == "CLINICALLY_IRRELEVANT":
                continue

            s = self.score(query, disease, e)
            e_copy = dict(e)
            e_copy["trust_score"] = s
            e_copy["source_name"] = e.get("source") or "Medical Knowledge Base"
            e_copy["source_verified"] = True if e.get("source") else False
            e_copy["kg_verified"] = True
            e_copy["explanation_factors"] = {
                "disease_match": filter_info.get("disease_match", True),
                "treatment_match": filter_info.get("treatment_match", True),
                "source_verified": e_copy["source_verified"],
                "kg_consistent": True,
                "reason": f"Directly supports clinical information for {disease}." if filter_info.get("disease_match") else "Supports clinical context for query."
            }
            scored.append(e_copy)

        scored.sort(key=lambda x: x["trust_score"], reverse=True)
        return scored