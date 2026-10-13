from datasets import load_dataset
import json
from pathlib import Path

OUTPUT = "data/raw/pubmed/pubmedqa.jsonl"

Path("data/raw/pubmed").mkdir(parents=True, exist_ok=True)

dataset = load_dataset("qiaojin/PubMedQA", "pqa_labeled")

with open(OUTPUT, "w", encoding="utf8") as f:
    for item in dataset["train"]:
        record = {
            "id": item["pubid"],
            "question": item["question"],
            "context": " ".join(item["context"]["contexts"]),
            "answer": item["long_answer"]
        }
        f.write(json.dumps(record) + "\n")

print("✅ PubMedQA saved")