import json
import os
import time

from dotenv import load_dotenv

from retrieval.rag_retriever import MedicalRAG
from pipeline.trust_rank import MedicalTrustRank
from pipeline.q2_evaluator import Q2Evaluator

from scripts.metric_utils import (
    precision_at_k,
    recall_at_k,
    f1_at_k,
    content_relevance,
    mrr,
    ndcg
)

load_dotenv()

# -----------------------------
# Load filtered dataset
# -----------------------------
with open("data/processed/medquad_filtered.json") as f:
    medquad = json.load(f)

rag = MedicalRAG()
trust = MedicalTrustRank()
q2_evaluator = None
if os.getenv("GEMINI_API_KEY"):
    q2_evaluator = Q2Evaluator(os.getenv("GEMINI_API_KEY"))

results = []

# -----------------------------
# Run over multiple queries
# -----------------------------
for i, item in enumerate(medquad[:50]):   # use 50 queries

    query = item.get("question", "")
    gold_answer = item.get("answer", "")

    if not query or not gold_answer:
        continue

    start_time = time.time()

    # -------------------------
    # RAG Retrieval
    # -------------------------
    retrieved = rag.retrieve(query, top_k=10)

    retrieved_ids = [r.get("text", "").lower() for r in retrieved]

    # -------------------------
    # TrustRank
    # -------------------------
    ranked = trust.rank(query, None, retrieved)

    ranked_ids = [r.get("text", "").lower() for r in ranked]

    # -------------------------
    # Ground truth proxy
    # -------------------------
    gold_ids = [gold_answer.lower()]

    # -------------------------
    # Metrics
    # -------------------------
    p5 = precision_at_k(ranked_ids, gold_ids, k=5)
    r5 = recall_at_k(ranked_ids, gold_ids, k=5)
    f1 = f1_at_k(ranked_ids, gold_ids, k=5)
    mrr_score = mrr(ranked_ids, gold_ids)

    ranking_relevance = [1 if rid in gold_ids else 0 for rid in ranked_ids[:5]]
    ndcg_score = ndcg(ranking_relevance)

    # -------------------------
    # Faithfulness
    # -------------------------
    combined_text = " ".join(ranked_ids)

    faithfulness = 1.0 if gold_answer.lower() in combined_text else 0.0
    hallucination = 1.0 - faithfulness
    content_score = content_relevance(query, ranked_ids[:5])
    q2_result = None
    if q2_evaluator:
        q2_result = q2_evaluator.score(gold_answer, combined_text)

    # -------------------------
    # Enrichment
    # -------------------------
    enrichment_used = 1 if len(retrieved) == 0 else 0

    # -------------------------
    # Latency
    # -------------------------
    latency = time.time() - start_time

    results.append({
        "query": query,
        "precision@5": p5,
        "recall@5": r5,
        "f1@5": f1,
        "mrr": mrr_score,
        "ndcg": ndcg_score,
        "faithfulness": faithfulness,
        "content_relevance": content_score,
        "q2": q2_result["score"] if q2_result else None,
        "q2_questions": q2_result["questions"] if q2_result else [],
        "q2_question_scores": q2_result["question_scores"] if q2_result else [],
        "hallucination": hallucination,
        "latency": latency,
        "enrichment": enrichment_used
    })

    print(f"✔ Processed {i+1}/50")

# -----------------------------
# Save results
# -----------------------------
with open("logs/final_metrics.json", "w") as f:
    json.dump(results, f, indent=2)

print("\n✅ Evaluation completed & saved")