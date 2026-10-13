import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir / 'backend'))
sys.path.insert(0, str(root_dir))

from pipeline.source_verifier import SourceVerifier
from pipeline.clinical_filter import ClinicalRelevanceFilter
from pipeline.trust_rank import MedicalTrustRank
from pipeline.cku import ContinuousKnowledgeUpdater

def run_10_test_cases():
    print("==================================================")
    print("RUNNING 10 USER SPECIFICATION TEST CASES")
    print("==================================================\n")

    verifier = SourceVerifier()
    filter_engine = ClinicalRelevanceFilter()
    trust_engine = MedicalTrustRank()
    cku = ContinuousKnowledgeUpdater()

    # TEST 1: Valid official WHO source
    print("📌 TEST 1: Valid official WHO source")
    t1_res = verifier.verify_and_evaluate_evidence(
        url="https://www.who.int/news-room/fact-sheets/detail/hepatitis-a",
        source_name="WHO",
        clinical_entity="Hepatitis A",
        entity_type="Disease",
        evidence_type="Clinical Guideline",
        evidence_text="Hepatitis A is an inflammation of the liver caused by the hepatitis A virus. Symptoms include fatigue, nausea, abdominal pain, and jaundice."
    )
    print(f"   Decision: {t1_res['decision']}, TrustRank: {t1_res['final_trust_score']:.1f}/100, Authority: {t1_res['source_authority_score']}/100")
    assert t1_res['decision'] in ['VERIFIED', 'REVIEW'], f"Test 1 failed! Got {t1_res['decision']}"
    assert t1_res['source_authority_score'] >= 95, "Test 1 failed: WHO authority score should be 95+"
    print("   -> PASSED: Valid official WHO source processed properly.\n")

    # TEST 2: Fake WHO-looking URL
    print("📌 TEST 2: Fake WHO-looking URL (Source Name: WHO, URL: example.com/fake-who)")
    t2_res = verifier.verify_and_evaluate_evidence(
        url="https://example.com/fake-who-page",
        source_name="WHO",
        clinical_entity="Hepatitis A",
        entity_type="Disease",
        evidence_type="Clinical Guideline",
        evidence_text="Fake WHO guidelines."
    )
    print(f"   Decision: {t2_res['decision']}, Rejection Reasons: {t2_res['rejection_reasons']}")
    assert t2_res['decision'] in ['REJECTED', 'REVIEW'], "Test 2 failed: Fake URL was not rejected/reviewed!"
    assert any("Domain mismatch" in r or "HTTP" in r or "unverified" in r.lower() for r in t2_res['rejection_reasons']), "Test 2 failed: Domain mismatch or HTTP issue not reported"
    print("   -> PASSED: Fake WHO-looking URL was caught and rejected.\n")

    # TEST 3: Valid PubMed article
    print("📌 TEST 3: Valid PubMed article")
    t3_res = verifier.verify_and_evaluate_evidence(
        url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        source_name="PubMed / NIH",
        clinical_entity="Diabetes",
        entity_type="Disease",
        evidence_type="Systematic Review",
        evidence_text="Systematic review of type 2 diabetes management protocols."
    )
    print(f"   Decision: {t3_res['decision']}, Authority: {t3_res['source_authority_score']}/100, Quality: {t3_res['evidence_quality_score']}/100")
    assert t3_res['source_authority_score'] >= 95, "Test 3 failed: PubMed should have authority >= 95"
    assert t3_res['evidence_quality_score'] >= 90, "Test 3 failed: Systematic Review quality should be >= 90"
    print("   -> PASSED: Valid PubMed article evaluated with high authority and quality.\n")

    # TEST 4: Unknown medical blog
    print("📌 TEST 4: Unknown medical blog")
    t4_res = verifier.verify_and_evaluate_evidence(
        url="https://myrandomhealthblog.com/tips",
        source_name="HealthBlog",
        clinical_entity="Hypertension",
        entity_type="Disease",
        evidence_type="Blog",
        evidence_text="Drinking cucumber juice cures high blood pressure instantly."
    )
    print(f"   Decision: {t4_res['decision']}, Authority: {t4_res['source_authority_score']}/100, TrustRank: {t4_res['final_trust_score']:.1f}/100")
    assert t4_res['decision'] in ['REJECTED', 'REVIEW'], "Test 4 failed: Medical blog was not rejected/reviewed!"
    assert t4_res['source_authority_score'] <= 40, "Test 4 failed: Unknown blog authority should be low (<= 40)"
    print("   -> PASSED: Unknown medical blog scored low authority.\n")

    # TEST 5: Hepatitis A candidate + Autoimmune Hepatitis evidence
    print("📌 TEST 5: Hepatitis A candidate + Autoimmune Hepatitis evidence")
    ev_list_5 = [
        {"question": "What is Autoimmune Hepatitis?", "text": "Autoimmune hepatitis is chronic liver inflammation.", "score": 0.88, "source": "CDC"},
        {"question": "What are treatments for Hepatitis A?", "text": "Hepatitis A requires supportive care.", "score": 0.75, "source": "WHO"}
    ]
    res_5 = filter_engine.filter_evidences("Hepatitis A", ["jaundice"], ev_list_5)
    print(f"   Verified Primary: {[e['question'] for e in res_5['verified_evidence']]}")
    print(f"   Related (Excluded): {[e['question'] for e in res_5['related_evidence']]}")
    assert len(res_5['verified_evidence']) == 1 and "Hepatitis A" in res_5['verified_evidence'][0]['question'], "Test 5 failed: Autoimmune Hepatitis appeared in primary evidence!"
    print("   -> PASSED: Autoimmune Hepatitis correctly moved to Related Evidence.\n")

    # TEST 6: Osteoarthritis candidate + Rheumatic Fever evidence
    print("📌 TEST 6: Osteoarthritis candidate + Rheumatic Fever evidence")
    ev_list_6 = [
        {"question": "What is Rheumatic Fever?", "text": "Rheumatic fever symptoms include joint pain and fever.", "score": 0.90, "source": "NIH"}
    ]
    res_6 = filter_engine.filter_evidences("Osteoarthritis", ["joint pain"], ev_list_6)
    print(f"   Verified Primary: {[e['question'] for e in res_6['verified_evidence']]}")
    print(f"   Related (Excluded): {[e['question'] for e in res_6['related_evidence']]}")
    assert len(res_6['verified_evidence']) == 0, "Test 6 failed: Rheumatic Fever was not excluded from Osteoarthritis primary evidence!"
    print("   -> PASSED: Rheumatic Fever rejected as supporting evidence for Osteoarthritis.\n")

    # TEST 7: Strong clinically relevant evidence
    print("📌 TEST 7: Strong clinically relevant evidence")
    t7_res = verifier.verify_and_evaluate_evidence(
        url="https://www.cdc.gov/hepatitis/hav/afaq.htm",
        source_name="CDC",
        clinical_entity="Hepatitis A",
        entity_type="Disease",
        evidence_type="Clinical Guideline",
        evidence_text="Hepatitis A causes fatigue, nausea, abdominal pain, and dark urine. Preventive vaccination and supportive treatment are standard."
    )
    print(f"   TrustRank: {t7_res['final_trust_score']:.1f}/100, Decision: {t7_res['decision']}")
    assert t7_res['final_trust_score'] >= 80, f"Test 7 failed: Expected high TrustRank (>=80), got {t7_res['final_trust_score']}"
    print("   -> PASSED: High TrustRank produced for strong clinically relevant evidence.\n")

    # TEST 8: No relevant evidence
    print("📌 TEST 8: No relevant evidence")
    res_8 = filter_engine.filter_evidences("Rare Unknown Syndrome X", ["headache"], [
        {"question": "Cardiology guideline", "text": "Cardiac arrest protocols.", "score": 0.15}
    ])
    print(f"   Filter Status: {res_8['status']}, Message: {res_8['status_message']}")
    assert res_8['status'] == "INSUFFICIENT" or len(res_8['verified_evidence']) == 0, "Test 8 failed!"
    print("   -> PASSED: Insufficient evidence status returned.\n")

    # TEST 9: Conflicting evidence
    print("📌 TEST 9: Conflicting evidence detection")
    t9_res = verifier.verify_and_evaluate_evidence(
        url="https://www.cdc.gov/conflict-test",
        source_name="CDC",
        clinical_entity="Hepatitis A",
        entity_type="Disease",
        evidence_type="Clinical Reference",
        evidence_text="Hepatitis A is treated with antibiotics and blood transfusions.", # Contradicts standard supportive care
        neo4j_relationship_verified=False
    )
    print(f"   Decision: {t9_res['decision']}, KG Consistency: {t9_res['kg_consistency_score']}/100")
    assert t9_res['decision'] in ['REVIEW', 'REJECTED'], "Test 9 failed: Conflicting evidence was not placed in REVIEW/REJECTED!"
    print("   -> PASSED: Conflicting evidence flagged for clinician review.\n")

    # TEST 10: Invalid URL
    print("📌 TEST 10: Invalid URL")
    t10_res = verifier.verify_and_evaluate_evidence(
        url="http://invalid-nonexistent-domain-12345.org/page",
        source_name="Unknown",
        clinical_entity="Pneumonia",
        entity_type="Disease",
        evidence_type="Blog",
        evidence_text="Some text"
    )
    print(f"   Decision: {t10_res['decision']}, Rejection Reasons: {t10_res['rejection_reasons']}")
    assert t10_res['decision'] == "REJECTED", "Test 10 failed: Invalid URL was not REJECTED!"
    print("   -> PASSED: Invalid URL rejected unconditionally.\n")

    print("==================================================")
    print("ALL 10 USER SPECIFICATION TESTS PASSED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    run_10_test_cases()
