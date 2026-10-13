import json

with open("logs/final_metrics.json") as f:
    data = json.load(f)

n = len(data)


def avg(key):
    return sum(d.get(key, 0.0) for d in data) / n if n > 0 else 0.0


print("\n📊 ACCURATE FINAL EVALUATION METRICS (AVERAGED):\n")

print(f"Total Queries Evaluated : {n}")
print(f"Precision@5             : {avg('precision@5'):.4f}")
print(f"Recall@5                : {avg('recall@5'):.4f}")
print(f"F1-Score@5              : {avg('f1@5'):.4f}")
print(f"MRR                     : {avg('mrr'):.4f}")
print(f"nDCG                    : {avg('ndcg'):.4f}")
print(f"Faithfulness            : {avg('faithfulness'):.4f}")
print(f"Hallucination Rate      : {avg('hallucination'):.4f}")
print(f"Latency (seconds)       : {avg('latency'):.4f}")
print(f"Enrichment Usage        : {avg('enrichment'):.4f}")