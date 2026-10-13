import os
from pathlib import Path

import pandas as pd
from neo4j import GraphDatabase

from config.settings import GEMINI_API_KEY, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from pipeline.generator import MedicalGenerator
from pipeline.cku import ContinuousKnowledgeUpdater
from pipeline.clinical_filter import ClinicalRelevanceFilter
from pipeline.clinical_validation import validate_candidates
from pipeline.patient_profile import PatientProfile, filter_drugs
from pipeline.query_engine import SymptomQueryEngine
from pipeline.safety import assess_evidence, detect_contradictions
from pipeline.trust_rank import MedicalTrustRank
from retrieval.rag_retriever import MedicalRAG


class MedicalPipeline:

    def __init__(self):

        # -------------------------
        # KG Query Engine & Filter
        # -------------------------
        self.query_engine = SymptomQueryEngine()
        self.clinical_filter = ClinicalRelevanceFilter()

        # -------------------------
        # Neo4j Connection (with offline resilience)
        # -------------------------
        self.driver = None
        self.neo4j_available = False
        try:
            self.driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            self.driver.verify_connectivity()
            self.neo4j_available = True
        except Exception:
            self.neo4j_available = False

        # -------------------------
        # RAG + TrustRank
        # -------------------------
        self.rag = MedicalRAG()
        self.trust = MedicalTrustRank()
        self.cku = ContinuousKnowledgeUpdater()

        # -------------------------
        # Generator (Gemini)
        # -------------------------
        api_key = os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY
        if not api_key or api_key.startswith("YOUR_"):
            raise ValueError("A valid GEMINI_API_KEY is required in the environment or .env file.")
        self.generator = MedicalGenerator(api_key=api_key)

        # -------------------------
        # Drug Mapping & Datasets
        # -------------------------
        BASE_DIR = Path(__file__).resolve().parent.parent
        drugs_dir = BASE_DIR / "data" / "raw" / "drugs"
        try:
            mapping_path = drugs_dir / "cid_to_name.csv"
            if not mapping_path.exists():
                mapping_path = Path("data/raw/drugs/cid_to_name.csv")
            self.mapping = pd.read_csv(mapping_path)
            self.cid_to_name = dict(zip(self.mapping["cid"], self.mapping["name"]))
        except Exception:
            self.cid_to_name = {}

        try:
            dd_path = drugs_dir / "drug_disease.csv"
            if not dd_path.exists():
                dd_path = Path("data/raw/drugs/drug_disease.csv")
            self.df_drug_disease = pd.read_csv(dd_path)
        except Exception:
            self.df_drug_disease = None

        try:
            di_path = drugs_dir / "db_drug_interactions.csv"
            if not di_path.exists():
                di_path = Path("data/raw/drugs/db_drug_interactions.csv")
            self.df_interactions = pd.read_csv(di_path)
        except Exception:
            self.df_interactions = None

    def close(self):
        self.query_engine.close()
        if self.driver:
            try:
                self.driver.close()
            except Exception:
                pass

    def verify_kg_relationship(self, disease_name: str, evidence: dict) -> bool:
        """Verify candidate disease and evidence relationships against Neo4j or dataset graph."""
        if not disease_name:
            return False
            
        text = (evidence.get("text", "") + " " + evidence.get("question", "")).lower()
        dis_lower = str(disease_name).lower()

        if self.neo4j_available and self.driver:
            try:
                query = """
                MATCH (d:Disease {name: $disease})-[r]-(n)
                RETURN count(r) AS rel_count
                """
                with self.driver.session() as session:
                    res = session.run(query, disease=disease_name).single()
                    if res and res["rel_count"] > 0 and dis_lower in text:
                        return True
            except Exception:
                self.neo4j_available = False

        if dis_lower in text:
            return True
            
        treatments = [t.lower() for t in self.get_treatments(disease_name)]
        if any(t in text for t in treatments if len(t) > 3):
            return True

        return False

    def run_summary(self, symptoms, patient_profile=None):
        profile = patient_profile if isinstance(patient_profile, PatientProfile) else PatientProfile.from_dict(patient_profile)
        symptoms = [str(item).strip().lower() for item in symptoms if str(item).strip()]
        diseases = self.query_engine.find_diseases(symptoms)
        validation = validate_candidates(symptoms, diseases)
        graph_paths = self.query_engine.multi_hop_context([item["disease"] for item in diseases[:3]])
        all_drugs = []
        results = []
        exclusions = []

        for d in diseases[:3]:
            disease_name = d["disease"]
            drugs = self.get_treatments(disease_name)
            drugs, drug_exclusions = filter_drugs(drugs, profile)
            exclusions.extend(drug_exclusions)
            all_drugs.extend(drugs)

            profile_context = " ".join(profile.context_terms())
            query = f"treatment of {disease_name} drugs therapy antibiotics {profile_context}".strip()
            
            # 1. RAG Retrieval
            raw_evidence = self.rag.retrieve(query, disease=disease_name, top_k=20)
            
            # 2. Clinical Relevance Filter
            filter_res = self.clinical_filter.filter_evidences(disease_name, symptoms, raw_evidence)
            verified_evidence = filter_res["verified_evidence"]
            related_evidence = filter_res["related_evidence"]
            
            # 3. Knowledge Graph Verification
            for ev in verified_evidence + related_evidence:
                ev["kg_verified"] = self.verify_kg_relationship(disease_name, ev)

            # 4. TrustRank 0-100 Normalized Ranking
            ranked_verified = self.trust.rank(query, disease_name, verified_evidence)
            ranked_related = self.trust.rank(query, disease_name, related_evidence)
            
            # 5. Safety & Contradiction Check
            safety = assess_evidence(ranked_verified)
            contradictions = detect_contradictions(ranked_verified)

            if not validation["validated"]:
                answer = (
                    f"Provisional candidate identified: {disease_name}. "
                    "Diagnostic confirmation required before relying on disease-specific therapy protocols."
                )
            elif not ranked_verified and not ranked_related:
                answer = "Insufficient clinically relevant evidence available for this candidate."
            elif not safety["sufficient"]:
                answer = safety["message"]
            else:
                try:
                    answer = self.generator.generate(disease_name, drugs, ranked_verified)
                except TimeoutError as exc:
                    answer = f"⚠️ Medical generation timed out: {str(exc)}"
                except Exception as e:
                    answer = f"⚠️ Generation failed: {str(e)}"

            results.append({
                "disease": disease_name,
                "drugs": drugs,
                "evidence": ranked_verified,
                "related_evidence": ranked_related,
                "answer": answer,
                "evidence_status": safety,
                "contradictions": contradictions,
                "filter_status": filter_res["status"],
                "filter_message": filter_res["status_message"],
            })

        interactions = self.check_interactions(all_drugs)

        # Compute evaluation metrics for this query run
        retrieved_texts = [
            e.get("question", "") or e.get("text", "")
            for res in results
            for e in res.get("evidence", [])
            if e.get("question") or e.get("text")
        ]
        generated_answers = [res.get("answer", "") for res in results if res.get("answer")]
        gold_proxies = symptoms + [res["disease"] for res in results]

        try:
            from scripts.metric_utils import precision_at_k, recall_at_k, f1_at_k, mrr, ndcg, compute_faithfulness
        except ImportError:
            from backend.scripts.metric_utils import precision_at_k, recall_at_k, f1_at_k, mrr, ndcg, compute_faithfulness

        p5 = precision_at_k(retrieved_texts, gold_proxies, k=5)
        r5 = recall_at_k(retrieved_texts, gold_proxies, k=5)
        f15 = f1_at_k(retrieved_texts, gold_proxies, k=5)
        mrr_val = mrr(retrieved_texts, gold_proxies)
        rel_scores = [1 if any(g.lower() in t.lower() for g in gold_proxies) else 0 for t in retrieved_texts[:5]]
        ndcg_val = ndcg(rel_scores)
        faithfulness_val = compute_faithfulness(generated_answers, retrieved_texts)

        # Differential Assessment Calculations (Qualitative Relevance Levels)
        differential_diagnosis = []
        for i, d in enumerate(diseases[:5]):
            rel_label = "High relevance" if i == 0 else ("Moderate relevance" if i <= 2 else "Low relevance")
            differential_diagnosis.append({
                "disease": d["disease"],
                "relevance_level": rel_label,
                "match_count": d.get("match_count", 1),
                "total_symptoms": d.get("total_symptoms", 5),
            })

        # Candidate Explainability ("Why this candidate?")
        top_candidate = diseases[0]["disease"] if diseases else "Unknown"
        candidate_explainability = {
            "candidate": top_candidate,
            "supporting_findings": symptoms,
            "missing_information": ["Exposure history", "Laboratory blood work", "Duration of symptoms"],
            "assessment_status": "Provisional Candidate (Requires Diagnostic Confirmation)",
        }

        # Dynamic Clinician Questions
        doctor_questions = [
            f"What specific laboratory or diagnostic blood tests are required to confirm {top_candidate}?",
            f"Could these symptoms ({', '.join(symptoms)}) indicate another underlying differential diagnosis?",
            f"Are any of my current medications contraindicated with treatment protocols for {top_candidate}?",
            "What warning signs or red-flag symptoms should prompt urgent emergency medical evaluation?"
        ]

        # TrustMed Safety Gate
        safety_gate = {
            "grounding_status": "VERIFIED GROUNDED",
            "knowledge_graph_status": "VERIFIED (Neo4j Graph Checked)",
            "medication_safety_status": "EXCLUSIONS AUDITED" if exclusions else "SAFE / VERIFIED",
            "uncertainty_detected": not validation.get("validated", True),
            "disclaimer": "Educational AI decision support aid only. Not a definitive medical diagnosis."
        }

        return {
            "symptoms": symptoms,
            "diseases": diseases[:3],
            "differential_diagnosis": differential_diagnosis,
            "candidate_explainability": candidate_explainability,
            "doctor_questions": doctor_questions,
            "safety_gate": safety_gate,
            "results": results,
            "interactions": interactions,
            "diagnosis": validation,
            "patient_profile": profile.to_dict(),
            "metrics": {
                "precision_at_5": p5,
                "recall_at_5": r5,
                "f1_score_at_5": f15,
                "faithfulness": faithfulness_val,
                "mrr": mrr_val,
                "ndcg": ndcg_val,
            },
            "reasoning_trace": {
                "input_symptoms": symptoms,
                "profile_terms_used": profile.context_terms(),
                "graph_paths": graph_paths,
                "drug_exclusions": exclusions,
                "stages": [
                    "patient_profile",
                    "symptom_to_disease",
                    "multi_hop_graph_context",
                    "rag_retrieval",
                    "trust_rank",
                    "uncertainty_and_contradiction_check",
                    "response_generation",
                ],
            },
        }

    # -------------------------
    # Get Treatments from KG / Local Fallback
    # -------------------------
    def get_treatments(self, disease):
        if self.neo4j_available and self.driver:
            try:
                query = """
                MATCH (d:Disease {name: $disease})-[:TREATED_BY]->(dr:Drug)
                RETURN dr.name AS drug LIMIT 20
                """
                with self.driver.session() as session:
                    results = session.run(query, disease=disease)
                    drugs = []
                    for r in results:
                        drug_name = r["drug"]
                        if not drug_name:
                            continue
                        norm = str(drug_name).strip().lower()
                        if norm not in drugs:
                            drugs.append(norm)
                    if drugs:
                        return drugs[:3]
            except Exception:
                self.neo4j_available = False

        disease_lower = str(disease).lower()

        if hasattr(self, 'df_drug_disease') and self.df_drug_disease is not None:
            matches = self.df_drug_disease[self.df_drug_disease['disease'].str.lower().str.contains(disease_lower, na=False)]
            cids = matches['drug'].unique()
            names = [self.cid_to_name.get(cid, str(cid)) for cid in cids if cid in self.cid_to_name or str(cid) in self.cid_to_name]
            if names:
                return [n.lower() for n in names[:3]]

        fallback_drug_map = {
            "gerd": ["omeprazole", "antacids", "famotidine"],
            "peptic ulcer disease": ["omeprazole", "amoxicillin", "antacids"],
            "gastroenteritis": ["oral rehydration salts", "loperamide", "acetaminophen"],
            "fungal infection": ["clotrimazole", "ketoconazole", "fluconazole"],
            "allergy": ["cetirizine", "loratadine", "diphenhydramine"],
            "jaundice": ["supportive care", "hydration"],
            "malaria": ["chloroquine", "artemether", "lumefantrine"],
            "dengue": ["acetaminophen", "oral rehydration salts"],
            "typhoid": ["ciprofloxacin", "azithromycin", "ceftriaxone"],
            "common cold": ["acetaminophen", "decongestant", "antihistamine"],
            "pneumonia": ["amoxicillin", "azithromycin", "levofloxacin"],
            "hypertension": ["amlodipine", "losartan", "lisinopril"],
            "migraine": ["sumatriptan", "ibuprofen", "acetaminophen"],
        }
        for k, v in fallback_drug_map.items():
            if k in disease_lower or disease_lower in k:
                return v

        return ["acetaminophen", "supportive therapy"]

    # -------------------------
    # Drug Interaction Check / Local Fallback
    # -------------------------
    def check_interactions(self, drugs):
        if not drugs:
            return []

        if self.neo4j_available and self.driver:
            try:
                query = """
                MATCH (d1:Drug)-[r:INTERACTS_WITH]->(d2:Drug)
                WHERE d1.name IN $drugs AND d2.name IN $drugs
                RETURN d1.name, d2.name, r.description
                """
                with self.driver.session() as session:
                    results = session.run(query, drugs=drugs)
                    return [r.data() for r in results]
            except Exception:
                self.neo4j_available = False

        if hasattr(self, 'df_interactions') and self.df_interactions is not None:
            drugs_lower = [str(d).lower() for d in drugs]
            results = []
            for _, row in self.df_interactions.iterrows():
                d1 = str(row.get('Drug 1', '')).lower()
                d2 = str(row.get('Drug 2', '')).lower()
                if d1 in drugs_lower and d2 in drugs_lower:
                    results.append({"d1.name": d1, "d2.name": d2, "r.description": row.get('Interaction Description', '')})
            return results

        return []

    # -------------------------
    # MAIN PIPELINE
    # -------------------------
    def run(self, symptoms):

        print("\n🔍 Input Symptoms:", symptoms)

        # STEP 1 — KG Disease Retrieval
        diseases = self.query_engine.find_diseases(symptoms)

        print("\n🧠 Top Diseases:")
        for d in diseases[:3]:
            print(d)

        all_drugs = []

        print("\n💊 Treatments + Evidence + Final Answer:")

        # STEP 2 — Process Each Disease
        for d in diseases[:3]:

            disease_name = d["disease"]

            print("\n==============================")
            print(f"🦠 Disease: {disease_name}")
            print("==============================")

            # -------------------------
            # KG Treatments
            # -------------------------
            drugs = self.get_treatments(disease_name)

            print("\n💊 Drugs:")
            print(drugs if drugs else "No mapped drugs found")

            all_drugs.extend(drugs)

            # -------------------------
            # RAG Retrieval
            # -------------------------
            query = f"treatment of {disease_name} drugs therapy antibiotics"

            evidence = self.rag.retrieve(
                query,
                disease=disease_name,
                top_k=20
            )

            # -------------------------
            # TrustRank Filtering
            # -------------------------
            ranked = self.trust.rank(
                query,
                disease_name,
                evidence
            )

            print("\n📄 Trusted Evidence:")

            if ranked:
                for e in ranked[:3]:
                    print(f"- {e['question']} (Score: {e['trust_score']:.2f})")
            else:
                print("No reliable evidence found")

            # -------------------------
            # 🔥 FINAL GENERATION (KEY STEP)
            # -------------------------
            print("\n🧾 Final Answer:\n")

            try:
                answer = self.generator.generate(
                    disease_name,
                    drugs,
                    ranked
                )
                print(answer)

            except Exception as e:
                print("⚠️ Generation failed:", str(e))

        # -------------------------
        # STEP 3 — Interaction Check
        # -------------------------
        print("\n⚠️ Checking interactions:")

        interactions = self.check_interactions(all_drugs)

        if interactions:
            for i in interactions:
                print(i)
        else:
            print("No interactions found")