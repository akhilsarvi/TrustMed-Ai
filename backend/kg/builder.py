# kg/builder.py

import pandas as pd
from neo4j import GraphDatabase
from tqdm import tqdm
from config.settings import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


class MedicalKGBuilder:

    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD)
        )

    def close(self):
        self.driver.close()

    # ---------------------------
    # Constraints
    # ---------------------------
    def create_constraints(self):
        with self.driver.session() as session:
            session.run("""
                CREATE CONSTRAINT disease_name IF NOT EXISTS
                FOR (d:Disease) REQUIRE d.name IS UNIQUE
            """)
            session.run("""
                CREATE CONSTRAINT symptom_name IF NOT EXISTS
                FOR (s:Symptom) REQUIRE s.name IS UNIQUE
            """)
        print("✅ Constraints created")

    # ---------------------------
    # Insert Data
    # ---------------------------
    def insert_data(self, disease, symptoms):
        with self.driver.session() as session:
            session.execute_write(self._insert_tx, disease, symptoms)

    @staticmethod
    def _insert_tx(tx, disease, symptoms):

        # Create Disease
        tx.run(
            """
            MERGE (d:Disease {name: $disease})
            SET d.source = $source, d.confidence = $confidence
            """,
            disease=disease,
            source="DiseaseAndSymptoms",
            confidence=0.6
        )

        # Create Symptoms + Relations
        for symptom in symptoms:
            tx.run(
                """
                MERGE (s:Symptom {name: $symptom})
                WITH s
                MATCH (d:Disease {name: $disease})
                MERGE (d)-[:HAS_SYMPTOM]->(s)
                """,
                symptom=symptom,
                disease=disease
            )

        # Clique (Symptom co-occurrence)
        for i in range(len(symptoms)):
            for j in range(i + 1, len(symptoms)):
                tx.run(
                """
                MATCH (s1:Symptom {name: $s1})
                MATCH (s2:Symptom {name: $s2})
                MERGE (s1)-[r:CO_OCCURS_WITH]->(s2)
                ON CREATE SET r.weight = 1
                ON MATCH SET r.weight = r.weight + 1
                """,
                s1=symptoms[i],
                s2=symptoms[j]
            )

    # ---------------------------
    # Build from CSV
    # ---------------------------
    def build_from_csv(self, path):
        df = pd.read_csv(path)

        print(f"Loaded {len(df)} rows")

        for _, row in tqdm(df.iterrows(), total=len(df)):

            disease = str(row["Disease"]).strip().lower()

            symptoms = []
            for col in df.columns:
                if "Symptom" in col:
                    val = row[col]
                    if pd.notna(val):
                        clean = str(val).strip().replace("_", " ").lower()
                        symptoms.append(clean)

            symptoms = list(set(symptoms))

            if disease and symptoms:
                try:
                    self.insert_data(disease, symptoms)
                except Exception as e:
                    print(f"Error: {e}")

        print("✅ KG Build Complete")