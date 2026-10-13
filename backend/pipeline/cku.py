import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.source_verifier import SourceVerifier

BASE_DIR = Path(__file__).resolve().parent.parent


class ContinuousKnowledgeUpdater:
    """
    Continuous Knowledge Updation (CKU) Mechanism.
    Formalizes real HTTP source verification, domain authority scoring,
    evidence classification, deterministic TrustRank evaluation,
    and promotion into Neo4j & FAISS index.
    """

    def __init__(self, path: str | Path | None = None):
        if path is None:
            self.path = BASE_DIR / "logs" / "cku_candidates.jsonl"
        else:
            p = Path(path)
            self.path = p if p.is_absolute() else (BASE_DIR / p)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.verifier = SourceVerifier()

    def validate_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        raw_url = str(candidate.get("url") or candidate.get("source_url") or "").strip()
        user_source_name = str(candidate.get("source_name") or candidate.get("source", "")).strip()
        
        # If raw_url is empty but user_source_name starts with http, swap them
        if not raw_url and (user_source_name.startswith("http://") or user_source_name.startswith("https://") or "." in user_source_name):
            raw_url = user_source_name

        text = str(candidate.get("text", "")).strip()
        clinical_entity = str(candidate.get("clinical_entity") or candidate.get("disease", "")).strip()
        entity_type = str(candidate.get("entity_type", "Disease")).strip()
        category = str(candidate.get("category") or candidate.get("evidence_type", "General Medical Evidence")).strip()
        is_test_env = candidate.get("environment") == "TEST" or candidate.get("is_test", False)

        if not raw_url or not text:
            return {"status": "REJECTED", "reason": "Source URL and text are required fields"}

        candidate_id = candidate.get("id") or str(uuid.uuid4())[:8]

        # Perform Real HTTP Source Verification & Deterministic Audit Evaluation
        audit_trail = self.verifier.evaluate_full_candidate(
            raw_source_url=raw_url,
            text=text,
            clinical_entity=clinical_entity,
            entity_type=entity_type,
            category=category,
            user_source_name=user_source_name,
            is_test_env=is_test_env
        )

        decision = audit_trail["decision"]

        return {
            "id": candidate_id,
            "status": decision,
            "source": user_source_name or raw_url,
            "source_name": user_source_name,
            "source_url": raw_url,
            "text": text,
            "disease": clinical_entity,
            "clinical_entity": clinical_entity,
            "entity_type": entity_type,
            "category": category,
            "environment": "TEST" if is_test_env else "PRODUCTION",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "trust_score": audit_trail["final_trust_score"],
            "trust_rank": audit_trail["final_trust_score"],
            "audit_trail": audit_trail,
            "promoted": decision == "VERIFIED",
        }

    def submit(self, candidate: dict[str, Any]) -> dict[str, Any]:
        record = self.validate_candidate(candidate)
        if record.get("status") == "REJECTED":
            # Still save rejected candidate into staging log with audit trail for inspection
            records = self._load_all()
            records.append(record)
            self._save_all(records)
            return record

        records = self._load_all()
        for r in records:
            if r.get("text", "").strip().lower() == record["text"].strip().lower():
                return {"status": "DUPLICATE", "reason": "Identical medical evidence candidate already submitted", "existing_id": r.get("id")}

        records.append(record)
        self._save_all(records)
        return record

    def pending(self, limit: int = 50) -> list[dict[str, Any]]:
        records = self._load_all()
        pending_records = [r for r in records if r.get("status") in ["PENDING_REVIEW", "REVIEW"]]
        return pending_records[-limit:]

    def get_all(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._load_all()[-limit:]

    def get_evaluation(self, candidate_id: str) -> dict[str, Any] | None:
        records = self._load_all()
        for r in records:
            if str(r.get("id")) == str(candidate_id):
                return r
        return None

    def re_evaluate_all(self, neo4j_driver: Any = None) -> dict[str, Any]:
        records = self._load_all()
        updated = []
        verified_cnt = 0
        review_cnt = 0
        rejected_cnt = 0

        for r in records:
            payload = {
                "id": r.get("id"),
                "url": r.get("source_url") or r.get("url") or r.get("source"),
                "source_name": r.get("source_name") or r.get("source"),
                "text": r.get("text", ""),
                "clinical_entity": r.get("clinical_entity") or r.get("disease", ""),
                "entity_type": r.get("entity_type", "Disease"),
                "category": r.get("category") or r.get("evidence_type", "General Medical Evidence"),
                "environment": r.get("environment", "PRODUCTION")
            }
            new_record = self.validate_candidate(payload)
            if neo4j_driver and new_record.get("audit_trail"):
                # Re-check Neo4j graph relationships if driver available
                new_audit = self.verifier.who_verifier.verify_who_source(
                    raw_url=payload["url"],
                    user_source_name=payload["source_name"],
                    clinical_entity=payload["clinical_entity"],
                    evidence_type=payload["category"],
                    evidence_text=payload["text"],
                    use_cache=False,
                    neo4j_driver=neo4j_driver
                )
                new_record["audit_trail"] = new_audit
                new_record["status"] = new_audit["decision"]
                new_record["trust_score"] = new_audit["final_trust_score"]
                new_record["trust_rank"] = new_audit["final_trust_score"]

            st = new_record.get("status")
            if st == "VERIFIED":
                verified_cnt += 1
            elif st == "REVIEW":
                review_cnt += 1
            else:
                rejected_cnt += 1
            updated.append(new_record)

        self._save_all(updated)
        return {
            "status": "SUCCESS",
            "total_re_evaluated": len(updated),
            "verified_count": verified_cnt,
            "review_count": review_cnt,
            "rejected_count": rejected_cnt
        }

    def promote(self, candidate_id: str, neo4j_driver: Any = None, rag_retriever: Any = None) -> dict[str, Any]:
        """Promote a candidate into active Knowledge Base (Neo4j & FAISS index)."""
        records = self._load_all()
        target = None
        for r in records:
            if r.get("id") == candidate_id:
                target = r
                break

        if not target:
            return {"status": "ERROR", "reason": f"Candidate ID '{candidate_id}' not found"}

        if target.get("promoted") and target.get("status") == "VERIFIED":
            return {"status": "ALREADY_PROMOTED", "candidate": target}

        target["status"] = "VERIFIED"
        target["promoted"] = True
        target["promoted_at"] = datetime.now(timezone.utc).isoformat()

        if neo4j_driver:
            try:
                with neo4j_driver.session() as session:
                    session.run(
                        """
                        MERGE (f:MedicalFact {text: $text})
                        SET f.source = $source,
                            f.trust_score = $trust_score,
                            f.promoted_at = $promoted_at,
                            f.disease = $disease,
                            f.environment = $environment
                        """,
                        text=target["text"],
                        source=target["source"],
                        trust_score=target["trust_score"],
                        promoted_at=target["promoted_at"],
                        disease=target.get("disease", ""),
                        environment=target.get("environment", "PRODUCTION"),
                    )
            except Exception as e:
                target["neo4j_error"] = str(e)

        if rag_retriever:
            try:
                rag_retriever.add_document(
                    doc_id=target["id"],
                    text=target["text"],
                    metadata={
                        "source": target["source"],
                        "trust_score": target["trust_score"],
                        "disease": target.get("disease", ""),
                        "environment": target.get("environment", "PRODUCTION")
                    }
                )
            except Exception as e:
                target["faiss_error"] = str(e)

        self._save_all(records)
        return {"status": "SUCCESS", "promoted_candidate": target}

    def reject(self, candidate_id: str, reason: str = "Rejected during clinical audit") -> dict[str, Any]:
        records = self._load_all()
        target = None
        for r in records:
            if r.get("id") == candidate_id:
                target = r
                break

        if not target:
            return {"status": "ERROR", "reason": f"Candidate ID '{candidate_id}' not found"}

        target["status"] = "REJECTED"
        target["rejection_reason"] = reason
        if "audit_trail" in target:
            target["audit_trail"]["rejection_reasons"].append(reason)
            target["audit_trail"]["decision"] = "REJECTED"
        target["rejected_at"] = datetime.now(timezone.utc).isoformat()
        self._save_all(records)
        return {"status": "SUCCESS", "rejected_candidate": target}

    def auto_process_pending(
        self,
        trust_threshold: float = 75.0,
        reject_threshold: float = 50.0,
        neo4j_driver: Any = None,
        rag_retriever: Any = None,
    ) -> dict[str, Any]:
        """
        Automates evaluation of pending CKU candidates.
        Candidates with trust_score >= 75.0 are promoted to VERIFIED.
        Candidates with trust_score < 50.0 are REJECTED.
        """
        records = self._load_all()
        promoted = []
        rejected = []
        remaining = []

        for item in records:
            if item.get("status") in ["VERIFIED", "REJECTED"] and item.get("promoted"):
                continue

            t_score = float(item.get("trust_score", 0.0))
            candidate_id = item.get("id")
            if not candidate_id:
                continue

            if t_score >= trust_threshold and item.get("status") != "REJECTED":
                res = self.promote(candidate_id, neo4j_driver=neo4j_driver, rag_retriever=rag_retriever)
                promoted.append({"id": candidate_id, "source": item.get("source"), "trust_score": t_score, "result": res})
            elif t_score < reject_threshold or item.get("status") == "REJECTED":
                res = self.reject(candidate_id, reason=f"Automated audit: Trust score {t_score}/100 below threshold {reject_threshold}")
                rejected.append({"id": candidate_id, "source": item.get("source"), "trust_score": t_score, "result": res})
            else:
                remaining.append({"id": candidate_id, "source": item.get("source"), "trust_score": t_score})

        return {
            "status": "SUCCESS",
            "processed_count": len(promoted) + len(rejected),
            "promoted_count": len(promoted),
            "rejected_count": len(rejected),
            "remaining_pending_count": len(remaining),
            "promoted": promoted,
            "rejected": rejected,
            "remaining": remaining,
        }

    def seed_demo_candidates(self, force_reset: bool = True) -> list[dict[str, Any]]:
        """Seeds benchmark medical candidates into staging queue with environment='TEST'."""
        demo_candidates = [
            {
                "source": "https://www.who.int/news-room/fact-sheets/detail/hepatitis-a",
                "text": "Hepatitis A is an acute infectious liver disease caused by the hepatitis A virus. Symptoms include yellow skin, nausea, fatigue, fever, and abdominal pain.",
                "clinical_entity": "Hepatitis A",
                "entity_type": "Disease",
                "category": "Clinical Guidelines",
                "environment": "TEST"
            },
            {
                "source": "https://pubmed.ncbi.nlm.nih.gov/38491023/",
                "text": "Randomized controlled trial shows hydration therapy reduces headache duration by 40% in viral fever patients.",
                "clinical_entity": "fever",
                "entity_type": "Symptom",
                "category": "Randomized Controlled Trial",
                "environment": "TEST"
            },
            {
                "source": "https://unverified-blog.xyz/quick-cure-fever",
                "text": "Unverified blog claim: Drink raw garlic juice every hour to cure viral infection in 10 minutes.",
                "clinical_entity": "fever",
                "entity_type": "Symptom",
                "category": "Blog Post",
                "environment": "TEST"
            }
        ]

        results = []
        for cand in demo_candidates:
            res = self.submit(cand)
            results.append(res)
        return results

    def _load_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        modified = False
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if not record.get("id"):
                            record["id"] = str(uuid.uuid4())[:8]
                            modified = True
                        records.append(record)
                    except json.JSONDecodeError:
                        continue
        if modified:
            self._save_all(records)
        return records

    def _save_all(self, records: list[dict[str, Any]]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            for r in records:
                handle.write(json.dumps(r, ensure_ascii=True) + "\n")


