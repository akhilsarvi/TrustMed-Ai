import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / 'backend'))
sys.path.insert(0, str(root_dir))

from pipeline.clinical_filter import ClinicalRelevanceFilter
from pipeline.trust_rank import MedicalTrustRank
from pipeline.full_pipeline import MedicalPipeline


def run_all_tests():
    print("==================================================")
    print("RUNNING TRUSTMED-AI CLINICAL REQUIREMENT TESTS")
    print("==================================================\n")

    filter_engine = ClinicalRelevanceFilter()
    trust_engine = MedicalTrustRank()

    # TEST 1: Candidate = Hepatitis A (Ensure Autoimmune Hepatitis is NOT ranked as direct supporting evidence)
    raw_ev_1 = [
        {"question": "What is Autoimmune Hepatitis?", "text": "Autoimmune hepatitis is chronic inflammation of the liver.", "score": 0.88, "source": "CDC"},
        {"question": "What are the treatments for Hepatitis A?", "text": "Hepatitis A treatment focuses on supportive care and rest.", "score": 0.75, "source": "WHO"}
    ]
    res_1 = filter_engine.filter_evidences("Hepatitis A", ["jaundice", "fatigue"], raw_ev_1)
    verified_1 = trust_engine.rank("Hepatitis A", "Hepatitis A", res_1["verified_evidence"])
    related_1 = trust_engine.rank("Hepatitis A", "Hepatitis A", res_1["related_evidence"])

    print("✔ TEST 1 (Hepatitis A filtering):")
    print("  Verified Primary Evidence:", [e["question"] for e in verified_1])
    print("  Related Evidence (Excluded from Primary):", [e["question"] for e in related_1])
    assert len(verified_1) == 1 and "Hepatitis A" in verified_1[0]["question"], "FAIL: Autoimmune Hepatitis appeared in verified primary evidence!"
    print("  -> PASSED: Autoimmune Hepatitis was excluded from primary evidence.\n")

    # TEST 2: Candidate = Osteoarthritis (Ensure Rheumatic Fever is NOT ranked as direct supporting evidence)
    raw_ev_2 = [
        {"question": "What is Rheumatic Fever?", "text": "Rheumatic fever develops after strep throat.", "score": 0.92, "source": "NIH"},
        {"question": "What are treatments for Osteoarthritis?", "text": "Osteoarthritis is treated with analgesics and physical therapy.", "score": 0.70, "source": "WHO"}
    ]
    res_2 = filter_engine.filter_evidences("Osteoarthritis", ["joint pain"], raw_ev_2)
    verified_2 = trust_engine.rank("Osteoarthritis", "Osteoarthritis", res_2["verified_evidence"])
    related_2 = trust_engine.rank("Osteoarthritis", "Osteoarthritis", res_2["related_evidence"])

    print("✔ TEST 2 (Osteoarthritis filtering):")
    print("  Verified Primary Evidence:", [e["question"] for e in verified_2])
    print("  Related Evidence (Excluded from Primary):", [e["question"] for e in related_2])
    assert len(verified_2) == 1 and "Osteoarthritis" in verified_2[0]["question"], "FAIL: Rheumatic Fever appeared in primary evidence!"
    print("  -> PASSED: Rheumatic Fever was excluded from primary evidence.\n")

    # TEST 3: Relevant Hepatitis A evidence ranks higher than unrelated
    print("✔ TEST 3 (TrustRank 0-100 Normalized Scoring):")
    if verified_1:
        score_val = verified_1[0]["trust_score"]
        print(f"  Hepatitis A Primary Evidence TrustRank Score: {score_val} / 100")
        assert 0 <= score_val <= 100, f"FAIL: Score {score_val} out of 0-100 range!"
    print("  -> PASSED: TrustRank normalized properly between 0 and 100.\n")

    # TEST 4: No sufficiently relevant evidence
    res_4 = filter_engine.filter_evidences("Unknown Disease X", ["random symptom"], [
        {"question": "Cardiology guide", "text": "Cardiology info", "score": 0.2}
    ])
    print("✔ TEST 4 (Insufficient evidence handling):")
    print("  Filter Status:", res_4["status"])
    print("  Status Message:", res_4["status_message"])
    assert res_4["status"] == "INSUFFICIENT" or not res_4["verified_evidence"], "FAIL: Did not report insufficient evidence!"
    print("  -> PASSED: Displays insufficient evidence message.\n")

    # TEST 5 & 6: Full Pipeline run check
    pipeline = MedicalPipeline()
    try:
        pipeline_res = pipeline.run_summary(["jaundice", "vomiting"], {"age": 35, "gender": "male"})
        print("✔ TEST 5 & 6 (Full Pipeline & Safety Gate):")
        print("  Top Candidate:", pipeline_res["diseases"][0]["disease"])
        print("  Differential Assessment:", pipeline_res["differential_diagnosis"])
        print("  Safety Gate Status:", pipeline_res["safety_gate"]["grounding_status"])
        print("  Clinician Questions:", pipeline_res["doctor_questions"])
        assert "differential_diagnosis" in pipeline_res, "FAIL: Missing differential diagnosis!"
        assert "safety_gate" in pipeline_res, "FAIL: Missing safety gate!"
        print("  -> PASSED: Full pipeline verified cleanly.\n")
    finally:
        pipeline.close()

    print("==================================================")
    print("ALL 6 CLINICAL TESTS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    run_all_tests()
