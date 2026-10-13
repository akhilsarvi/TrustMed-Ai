import numpy as np
import re


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(text).lower()))


def _is_relevant(retrieved_item: str, gold_items: list[str], threshold: float = 0.3) -> bool:
    ret_tokens = _tokens(retrieved_item)
    if not ret_tokens:
        return False
    for gold in gold_items:
        gold_toks = _tokens(gold)
        if not gold_toks:
            continue
        overlap = len(ret_tokens & gold_toks)
        if overlap / max(len(gold_toks), 1) >= threshold or overlap / len(ret_tokens) >= threshold:
            return True
        if str(retrieved_item).lower() in str(gold).lower() or str(gold).lower() in str(retrieved_item).lower():
            return True
    return False


# -----------------------------
# Precision@K
# -----------------------------
def precision_at_k(retrieved: list[str], gold: list[str], k: int = 5) -> float:
    if k <= 0 or not retrieved:
        return 0.0
    topk = retrieved[:k]
    hits = sum(1 for r in topk if _is_relevant(r, gold))
    return round(hits / len(topk), 4)


# -----------------------------
# Recall@K
# -----------------------------
def recall_at_k(retrieved: list[str], gold: list[str], k: int = 5) -> float:
    if not gold or not retrieved:
        return 0.0
    topk = retrieved[:k]
    gold_hits = sum(1 for g in gold if any(_is_relevant(r, [g]) for r in topk))
    score = gold_hits / max(len(gold), 1)
    if score == 0:
        hits = sum(1 for r in topk if _is_relevant(r, gold))
        score = hits / max(len(topk), 1)
    return round(min(1.0, score), 4)


# -----------------------------
# F1@K
# -----------------------------
def f1_at_k(retrieved: list[str], gold: list[str], k: int = 5) -> float:
    precision = precision_at_k(retrieved, gold, k)
    recall = recall_at_k(retrieved, gold, k)
    if precision + recall == 0:
        return 0.0
    f1 = 2 * (precision * recall) / (precision + recall)
    return round(f1, 4)


# -----------------------------
# Content relevance
# -----------------------------
def content_relevance(query: str, retrieved: list[str]) -> float:
    query_tokens = _tokens(query)
    evidence_tokens = _tokens(" ".join(retrieved))
    if not query_tokens:
        return 0.0
    return round(len(query_tokens & evidence_tokens) / len(query_tokens), 4)


# -----------------------------
# Faithfulness (Grounding of Generated Response in Retrieved Literature)
# -----------------------------
def compute_faithfulness(generated_answers: list[str], retrieved_texts: list[str]) -> float:
    if not generated_answers or not retrieved_texts:
        return 0.0
    ans_combined = " ".join(generated_answers)
    ans_toks = _tokens(ans_combined)
    if not ans_toks:
        return 0.0
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "to", "from", "in", "out",
        "on", "off", "over", "under", "again", "further", "then", "once",
        "here", "there", "when", "where", "why", "how", "all", "any", "both",
        "each", "few", "more", "most", "other", "some", "such", "no", "nor",
        "not", "only", "own", "same", "so", "than", "too", "very", "s", "t",
        "can", "will", "just", "don", "should", "now", "this", "that", "these",
        "those", "and", "but", "if", "or", "because", "as", "until", "while",
        "of", "at", "by", "for", "with", "about", "against", "between", "into",
        "through", "during", "before", "after", "above", "below", "must", "should",
        "may", "might", "could", "would", "patient", "disease", "treatment", "please"
    }
    informative_ans_toks = {t for t in ans_toks if t not in stop_words and len(t) > 1}
    if not informative_ans_toks:
        return 1.0
    ev_combined = " ".join(retrieved_texts)
    ev_toks = _tokens(ev_combined)
    grounded_count = sum(1 for t in informative_ans_toks if t in ev_toks)
    score = grounded_count / len(informative_ans_toks)
    return round(score, 4)


# -----------------------------
# Q^2 proxy for QA quality
# -----------------------------
def q2_proxy(faithfulness: float, relevance: float) -> float:
    """Combine grounding and answer relevance into one QA score."""
    return round(float((faithfulness * relevance) ** 0.5), 4)


# -----------------------------
# MRR
# -----------------------------
def mrr(retrieved: list[str], gold: list[str]) -> float:
    for i, r in enumerate(retrieved, start=1):
        if _is_relevant(r, gold):
            return round(1.0 / i, 4)
    return 0.0


# -----------------------------
# nDCG
# -----------------------------
def ndcg(relevance: list[int]) -> float:
    dcg = 0.0
    for i, rel in enumerate(relevance, start=1):
        dcg += (2**rel - 1) / np.log2(i + 1)

    ideal = sorted(relevance, reverse=True)
    idcg = 0.0
    for i, rel in enumerate(ideal, start=1):
        idcg += (2**rel - 1) / np.log2(i + 1)

    return round(float(dcg / idcg), 4) if idcg > 0 else 0.0



