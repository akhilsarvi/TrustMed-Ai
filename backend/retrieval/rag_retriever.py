import faiss
import json
from sentence_transformers import SentenceTransformer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VECTOR_DIR = BASE_DIR / "data" / "vector_store"
VECTOR_DIR.mkdir(parents=True, exist_ok=True)

FAISS_PATH = VECTOR_DIR / "medquad.faiss"
MAP_PATH = VECTOR_DIR / "medquad_map.json"


class MedicalRAG:

    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

        # load FAISS index
        if FAISS_PATH.exists():
            self.index = faiss.read_index(str(FAISS_PATH))
        else:
            self.index = faiss.IndexFlatL2(384)

        # load metadata
        if MAP_PATH.exists():
            with open(MAP_PATH, "r", encoding="utf8") as f:
                self.mapping = json.load(f)
        else:
            self.mapping = []

        self.faiss_path = FAISS_PATH
        self.map_path = MAP_PATH

        # 🔥 keep keywords once (not inside loop)
        self.KEYWORDS = [
            "treat", "therapy", "drug", "antibiotic",
            "medication", "prescribed", "treatment"
        ]

    def retrieve(self, query, disease=None, top_k=20):

        # encode query
        vec = self.model.encode([query]).astype("float32")

        # search FAISS
        distances, indices = self.index.search(vec, top_k)

        results = []

        # normalize disease
        disease = disease.lower() if disease else None

        for i, d in zip(indices[0], distances[0]):

            item = self.mapping[i]

            question = item.get("question", "").lower()
            answer = item.get("answer")

            # skip bad data
            if not answer:
                continue

            answer_lower = answer.lower()

            # 🔥 disease-aware filtering (balanced, not too strict)
            if disease:
                if disease not in question and disease not in answer_lower:
                    if len(results) >= 2:
                        continue

            # 🔥 keyword filtering (treatment-focused)
            if any(k in answer_lower for k in self.KEYWORDS):

                results.append({
                    "text": answer,
                    "question": item.get("question", ""),
                    "score": float(1 / (1 + d))
                })

        return results[:5]

    def add_document(self, doc_id: str, text: str, metadata: dict = None):
        """
        Dynamically adds a new document/evidence vector to FAISS index and metadata mapping.
        """
        if not text or not text.strip():
            return False

        metadata = metadata or {}
        vec = self.model.encode([text]).astype("float32")
        self.index.add(vec)

        entry = {
            "question": metadata.get("disease") or "CKU Ingested Evidence",
            "answer": text,
            "source": metadata.get("source", ""),
            "trust_score": metadata.get("trust_score", 0.0),
            "doc_id": doc_id,
        }
        self.mapping.append(entry)

        # Save index & metadata back to disk
        faiss.write_index(self.index, "data/vector_store/medquad.faiss")
        with open("data/vector_store/medquad_map.json", "w", encoding="utf8") as f:
            json.dump(self.mapping, f, indent=2, ensure_ascii=False)

        return True