import pandas as pd
from neo4j import GraphDatabase
from config.settings import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def normalize(text):
    return str(text).strip().lower()


class InteractionBuilder:

    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD)
        )

    def close(self):
        self.driver.close()

    def insert_interaction(self, d1, d2, desc):
        with self.driver.session() as session:
            session.execute_write(self._tx, d1, d2, desc)

    @staticmethod
    def _tx(tx, d1, d2, desc):
        tx.run("""
            MERGE (d1:Drug {name: $d1})
            MERGE (d2:Drug {name: $d2})
            MERGE (d1)-[r:INTERACTS_WITH]->(d2)
            SET r.description = $desc
        """, d1=d1, d2=d2, desc=desc)

    def build_from_csv(self, path):

        df = pd.read_csv(path)

        print(f"Loaded {len(df)} rows")

        success = 0

        for _, row in df.iterrows():

            drug1 = normalize(row["Drug 1"])
            drug2 = normalize(row["Drug 2"])
            desc = str(row["Interaction Description"]).strip()

            try:
                self.insert_interaction(drug1, drug2, desc)
                success += 1
            except Exception:
                pass

        print(f"✅ Inserted {success} interactions")