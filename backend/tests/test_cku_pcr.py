import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.patient_profile import PatientProfile, check_compatibility, filter_drugs
from pipeline.cku import ContinuousKnowledgeUpdater

def test_pcr():
    print("=== Testing Patient-Centric Recommendation (PCR) Safety Filters ===")
    
    # Patient 1: Pregnant woman with peptic ulcer history
    profile_pregnant = PatientProfile.from_dict({
        "age": 30,
        "gender": "female",
        "pregnancy_status": "pregnant",
        "allergies": ["penicillin"],
        "current_medications": ["prenatal vitamins"],
        "chronic_conditions": ["peptic ulcer"],
    })
    
    candidate_drugs = ["ibuprofen", "aspirin", "amoxicillin", "penicillin v", "acetaminophen"]
    allowed, exclusions = filter_drugs(candidate_drugs, profile_pregnant)
    
    print(f"Candidate Drugs: {candidate_drugs}")
    print(f"Allowed Drugs: {allowed}")
    print("Exclusion Traces:")
    for ex in exclusions:
        print(f"  - Excluded '{ex['candidate']}': {ex['reason']} (Matched: {ex['matched_profile_terms']})")
    
    assert "ibuprofen" not in allowed, "Ibuprofen should be excluded for pregnant patient with peptic ulcer"
    assert "penicillin v" not in allowed, "Penicillin v should be excluded for penicillin allergic patient"
    assert "acetaminophen" in allowed, "Acetaminophen should be allowed"
    print("✅ PCR Safety Filter tests PASSED!\n")

def test_cku():
    print("=== Testing Continuous Knowledge Updation (CKU) Mechanism ===")
    updater = ContinuousKnowledgeUpdater(path="logs/test_cku.jsonl")
    
    # 1. Test candidate submission & trust scoring
    candidate_high_trust = {
        "source": "https://www.who.int/news/item/medical-update",
        "text": "New clinical guidelines recommend early oral rehydration therapy for mild dehydration.",
        "disease": "dehydration"
    }
    
    res1 = updater.submit(candidate_high_trust)
    print(f"High Trust Candidate Submission Status: {res1['status']}, Trust Score T(N): {res1['trust_score']}")
    assert res1['trust_score'] > 0.8, "WHO source should receive high trust score > 0.8"
    
    # 2. Test candidate promotion
    promote_res = updater.promote(res1['id'])
    print(f"Promotion Result: {promote_res['status']}")
    assert promote_res['status'] == "SUCCESS", "Candidate promotion should succeed"
    
    # Cleanup test file
    Path("logs/test_cku.jsonl").unlink(missing_ok=True)
    print("✅ CKU Mechanism tests PASSED!\n")

def test_auto_cku():
    print("=== Testing Automated CKU Auto-Evaluation & Auto-Promotion ===")
    test_path = Path("logs/test_auto_cku.jsonl")
    test_path.unlink(missing_ok=True)
    updater = ContinuousKnowledgeUpdater(path=test_path)

    # 1. Seed demo candidates
    seeded = updater.seed_demo_candidates()
    print(f"Seeded {len(seeded)} candidate medical evidence entries.")

    # 2. Run automated processing
    auto_res = updater.auto_process_pending(trust_threshold=0.75, reject_threshold=0.60)
    print(f"Automated Processing Results: Promoted={auto_res['promoted_count']}, Rejected={auto_res['rejected_count']}, Remaining={auto_res['remaining_pending_count']}")

    assert auto_res['promoted_count'] >= 1, "At least 1 high-trust candidate (WHO/PubMed) should be auto-promoted"
    assert auto_res['rejected_count'] >= 1, "At least 1 low-trust candidate (unverified blog) should be auto-rejected"

    # Cleanup test file
    test_path.unlink(missing_ok=True)
    print("✅ Automated CKU Engine tests PASSED!\n")

if __name__ == "__main__":
    test_pcr()
    test_cku()
    test_auto_cku()
    print("🎉 All verification tests passed successfully!")
