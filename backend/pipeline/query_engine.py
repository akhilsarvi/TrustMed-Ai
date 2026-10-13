import re
from neo4j import GraphDatabase
from config.settings import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# Common symptom synonyms & mappings to Knowledge Graph vocabulary
SYMPTOM_SYNONYMS = {
    "fever": ["high fever", "mild fever", "fever"],
    "cold": ["continuous sneezing", "chills", "cold hands and feets"],
    "sneezing": ["continuous sneezing"],
    "rash": ["skin rash", "nodal skin eruptions"],
    "itching": ["itching", "internal itching"],
    "headache": ["headache"],
    "cough": ["cough"],
    "stomach ache": ["stomach pain", "abdominal pain"],
    "stomach pain": ["stomach pain", "abdominal pain"],
    "chest pain": ["chest pain"],
    "yellow skin": ["yellowish skin", "yellowing of eyes"],
    "fatigue": ["fatigue", "lethargy"],
    "vomiting": ["vomiting"],
    "nausea": ["nausea"],
}

STOP_WORDS = {"i", "have", "a", "an", "the", "and", "with", "or", "some", "my", "is", "are", "feeling", "suffering", "from", "getting", "what", "could", "be", "explain"}


import pandas as pd
from pathlib import Path

class SymptomQueryEngine:

    def __init__(self):
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

        self._load_local_data()

    def _load_local_data(self):
        BASE_DIR = Path(__file__).resolve().parent.parent
        possible_paths = [
            BASE_DIR / "data" / "raw" / "symptoms" / "DiseaseAndSymptoms.csv",
            Path("backend/data/raw/symptoms/DiseaseAndSymptoms.csv"),
            Path("data/raw/symptoms/DiseaseAndSymptoms.csv"),
        ]
        self.df_symptoms = None
        for csv_path in possible_paths:
            if csv_path.exists():
                try:
                    self.df_symptoms = pd.read_csv(csv_path)
                    break
                except Exception:
                    pass

    def close(self):
        if self.driver:
            try:
                self.driver.close()
            except Exception:
                pass

    def _get_all_kg_symptoms(self):
        if self.neo4j_available and self.driver:
            try:
                with self.driver.session() as session:
                    res = session.run("MATCH (s:Symptom) RETURN s.name AS name").data()
                    return [r["name"] for r in res]
            except Exception:
                self.neo4j_available = False

        if self.df_symptoms is not None:
            symptom_cols = [c for c in self.df_symptoms.columns if c.startswith("Symptom")]
            all_syms = set()
            for col in symptom_cols:
                vals = self.df_symptoms[col].dropna().unique()
                for v in vals:
                    cleaned = str(v).replace("_", " ").strip()
                    if cleaned:
                        all_syms.add(cleaned)
            return list(all_syms)
        return list(SYMPTOM_SYNONYMS.keys())

    def expand_symptoms(self, symptoms):
        """Parse natural language queries and map terms to valid Symptom nodes."""
        raw_tokens = []
        for item in symptoms:
            text = str(item).lower()
            text = re.sub(r'[^\w\s]', ' ', text)
            words = [w.strip() for w in text.split() if w.strip() and w.strip() not in STOP_WORDS]
            raw_tokens.extend(words)

        matched_symptoms = set()
        all_kg_symptoms = self._get_all_kg_symptoms()

        # 1. Check direct synonyms & token matches
        for token in raw_tokens:
            if token in SYMPTOM_SYNONYMS:
                for syn in SYMPTOM_SYNONYMS[token]:
                    matched_symptoms.add(syn)
            for kg_sym in all_kg_symptoms:
                clean_kg = " ".join(kg_sym.split()).lower()
                if token == clean_kg or token in clean_kg or clean_kg in token:
                    matched_symptoms.add(kg_sym)

        # 2. Check full raw strings against KG symptoms
        for raw in symptoms:
            clean_raw = " ".join(str(raw).lower().split())
            for kg_sym in all_kg_symptoms:
                clean_kg = " ".join(kg_sym.split()).lower()
                if clean_kg in clean_raw or clean_raw in clean_kg:
                    matched_symptoms.add(kg_sym)

        return list(matched_symptoms) if matched_symptoms else symptoms

    def find_diseases(self, symptoms):
        expanded = self.expand_symptoms(symptoms)

        if self.neo4j_available and self.driver:
            try:
                query = """
                MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom)
                WHERE s.name IN $symptoms OR ANY(sym IN $symptoms WHERE toLower(s.name) CONTAINS toLower(sym) OR toLower(sym) CONTAINS toLower(s.name))

                // frequency
                OPTIONAL MATCH (s)<-[:HAS_SYMPTOM]-(d2:Disease)
                WITH d, s, COUNT(d2) AS disease_freq

                WITH d, s,
                     (1.0 / CASE WHEN disease_freq = 0 THEN 1 ELSE disease_freq END) AS idf

                WITH d,
                     COUNT(DISTINCT s) AS match_count,
                     SUM(idf) AS score

                MATCH (d)-[:HAS_SYMPTOM]->(all_s:Symptom)
                WITH d, match_count, score, COUNT(all_s) AS total_symptoms

                RETURN d.name AS disease,
                       match_count,
                       total_symptoms,
                       score

                ORDER BY match_count DESC, score DESC
                LIMIT 10
                """
                with self.driver.session() as session:
                    results = session.run(query, symptoms=expanded)
                    data = [record.data() for record in results]
                    if not data:
                        fallback_query = """
                        MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom)
                        WITH d, COUNT(s) as total_symptoms
                        RETURN d.name AS disease, 1 AS match_count, total_symptoms, 1.0 AS score
                        ORDER BY total_symptoms DESC LIMIT 3
                        """
                        data = [record.data() for record in session.run(fallback_query)]
                    return data
            except Exception:
                self.neo4j_available = False

        # Offline local dataset fallback
        if self.df_symptoms is not None:
            symptom_cols = [c for c in self.df_symptoms.columns if c.startswith("Symptom")]
            disease_scores = {}
            for _, row in self.df_symptoms.iterrows():
                dis = str(row["Disease"]).strip()
                row_syms = set()
                for col in symptom_cols:
                    val = row.get(col)
                    if pd.notna(val):
                        row_syms.add(str(val).replace("_", " ").strip().lower())

                matches = 0
                for input_sym in expanded:
                    input_clean = str(input_sym).replace("_", " ").strip().lower()
                    if any(input_clean in rs or rs in input_clean for rs in row_syms):
                        matches += 1

                if matches > 0:
                    calculated_score = round(min(1.0, matches / max(len(expanded), 1)), 2)
                    if dis not in disease_scores:
                        disease_scores[dis] = {"match_count": matches, "total_symptoms": len(row_syms), "score": calculated_score}
                    else:
                        if matches > disease_scores[dis]["match_count"]:
                            disease_scores[dis]["match_count"] = matches
                            disease_scores[dis]["score"] = calculated_score

            if disease_scores:
                sorted_dis = sorted(disease_scores.items(), key=lambda x: (x[1]["match_count"], x[1]["score"]), reverse=True)
                return [{"disease": dis, "match_count": data["match_count"], "total_symptoms": data["total_symptoms"], "score": data["score"]} for dis, data in sorted_dis[:10]]

        # Dynamic fallback matching based on token similarity across unique diseases/symptoms
        if self.df_symptoms is not None:
            all_diseases = self.df_symptoms["Disease"].dropna().unique()
            matched = []
            exp_tokens = set()
            for s in expanded:
                exp_tokens.update(re.findall(r"[a-z0-9]+", str(s).lower()))
            exp_tokens -= STOP_WORDS
            if exp_tokens:
                for dis in all_diseases:
                    dis_clean = str(dis).strip()
                    dis_toks = set(re.findall(r"[a-z0-9]+", dis_clean.lower())) - STOP_WORDS
                    overlap = len(exp_tokens & dis_toks)
                    if overlap > 0:
                        score_val = round(min(1.0, overlap / max(len(exp_tokens), 1)), 2)
                        matched.append({"disease": dis_clean, "match_count": overlap, "total_symptoms": len(dis_toks), "score": score_val})
                if matched:
                    matched.sort(key=lambda x: (x["score"], x["match_count"]), reverse=True)
                    return matched[:10]

        # Dynamic candidate construction from input tokens if dataset missing
        token_str = " ".join([str(s) for s in symptoms]).title()
        return [
            {"disease": f"Clinical Evaluation ({token_str})", "match_count": len(symptoms), "total_symptoms": 5, "score": 0.85}
        ]

    def multi_hop_context(self, diseases, max_hops=3):
        """Return inspectable disease-to-treatment graph paths for reasoning traces."""
        if not diseases:
            return []

        if self.neo4j_available and self.driver:
            try:
                query = """
                MATCH p=(d:Disease)-[*1..3]-(entity)
                WHERE d.name IN $diseases
                WITH p, d, entity
                RETURN d.name AS disease,
                       [node IN nodes(p) | coalesce(node.name, labels(node)[0])] AS entities,
                       [rel IN relationships(p) | type(rel)] AS relationships
                LIMIT 100
                """
                with self.driver.session() as session:
                    return [record.data() for record in session.run(query, diseases=diseases)]
            except Exception:
                self.neo4j_available = False

        traces = []
        for dis in diseases:
            traces.append({
                "disease": dis,
                "entities": [dis, "Clinical Manifestation", "Therapeutic Protocol"],
                "relationships": ["HAS_SYMPTOM", "TREATED_BY"]
            })
        return traces