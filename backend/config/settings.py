import os
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7688")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# TrustRank Configurable Weights (Normalized sum = 1.0)
TRUSTRANK_WEIGHTS = {
    "semantic_similarity": float(os.getenv("TRUSTRANK_WEIGHT_SIMILARITY", 0.30)),
    "clinical_relevance": float(os.getenv("TRUSTRANK_WEIGHT_RELEVANCE", 0.30)),
    "source_reliability": float(os.getenv("TRUSTRANK_WEIGHT_SOURCE", 0.15)),
    "kg_consistency": float(os.getenv("TRUSTRANK_WEIGHT_KG", 0.15)),
    "evidence_quality": float(os.getenv("TRUSTRANK_WEIGHT_QUALITY", 0.10)),
}