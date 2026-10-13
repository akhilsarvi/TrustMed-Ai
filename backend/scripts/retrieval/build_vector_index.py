import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

INPUT = "data/raw/medquad/medquad.jsonl"
INDEX_PATH = "data/vector_store/medquad.faiss"
MAP_PATH = "data/vector_store/medquad_map.json"

model = SentenceTransformer("all-MiniLM-L6-v2")

texts = []
mapping = []

with open(INPUT, "r", encoding="utf8") as f:
    for line in f:
        item = json.loads(line)

        text = f"""
{item['answer']}
"""

        texts.append(text)
        mapping.append(item)

print("Encoding...")

embeddings = model.encode(texts, show_progress_bar=True)
embeddings = np.array(embeddings).astype("float32")

index = faiss.IndexFlatL2(embeddings.shape[1])
index.add(embeddings)

faiss.write_index(index, INDEX_PATH)

with open(MAP_PATH, "w") as f:
    json.dump(mapping, f)

print("✅ Vector DB built")