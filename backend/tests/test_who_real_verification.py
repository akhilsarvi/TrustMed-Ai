import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir / 'backend'))
sys.path.insert(0, str(root_dir))

from pipeline.who_verifier import WhoSourceVerifier
from pipeline.source_verifier import SourceVerifier

def run_who_real_tests():
    print("==================================================")
    print("RUNNING REAL WHO SOURCE VERIFICATION TEST SUITE")
    print("==================================================\n")

    who_verifier = WhoSourceVerifier()
    verifier = SourceVerifier()

    # TEST A: Real WHO health topic (Hepatitis A)
    print("📌 TEST A: Real WHO health topic (Hepatitis A)")
    res_a = who_verifier.verify_who_source(
        raw_url="https://www.who.int/news-room/fact-sheets/detail/hepatitis-a",
        user_source_name="WHO",
        clinical_entity="Hepatitis A",
        evidence_type="Clinical Guideline",
        evidence_text="Hepatitis A is an inflammation of the liver caused by the hepatitis A virus. Symptoms include fatigue, nausea, abdominal pain, and jaundice."
    )
    print(f"   Domain Verified: {res_a['who_domain_verified']}, HTTP Status: {res_a['http_status']}")
    print(f"   Publisher: {res_a['publisher']}, WHO API: {res_a['who_api_verified']}")
    print(f"   Decision: {res_a['decision']}, TrustRank: {res_a['final_trust_score']}/100")
    assert res_a['who_domain_verified'] is True, "Test A Failed: WHO domain was not verified!"
    assert res_a['http_status'] == 200, "Test A Failed: HTTP status should be 200"
    assert res_a['decision'] == "VERIFIED", f"Test A Failed: Expected VERIFIED, got {res_a['decision']}"
    print("   -> PASSED: Real WHO health topic verified cleanly.\n")

    # TEST B: Lookalike domain (who.int.fake-site.com)
    print("📌 TEST B: Lookalike WHO domain (who.int.fake-site.com)")
    res_b = who_verifier.verify_who_source(
        raw_url="https://who.int.fake-site.com/fake-who-guideline",
        user_source_name="WHO",
        clinical_entity="Hepatitis A",
        evidence_type="Clinical Guideline",
        evidence_text="Fake WHO guideline."
    )
    print(f"   Domain Verified: {res_b['who_domain_verified']}, Decision: {res_b['decision']}")
    print(f"   Rejection Reasons: {res_b['rejection_reasons']}")
    assert res_b['who_domain_verified'] is False, "Test B Failed: Lookalike domain was wrongly verified as WHO!"
    assert res_b['decision'] == "REJECTED", f"Test B Failed: Lookalike domain should be REJECTED, got {res_b['decision']}"
    print("   -> PASSED: Lookalike domain caught and rejected.\n")

    # TEST C: 404 WHO URL (Page does not exist on who.int)
    print("📌 TEST C: 404 WHO URL (https://www.who.int/non-existent-page-999999)")
    res_c = who_verifier.verify_who_source(
        raw_url="https://www.who.int/non-existent-page-999999",
        user_source_name="WHO",
        clinical_entity="Hepatitis A",
        evidence_type="Clinical Guideline",
        evidence_text="Hepatitis A protocol"
    )
    print(f"   HTTP Status: {res_c['http_status']}, Decision: {res_c['decision']}")
    print(f"   Rejection Reasons: {res_c['rejection_reasons']}")
    assert res_c['http_status'] in (404, 403, 400), "Test C Failed: 404 WHO page did not return 404/403"
    assert res_c['decision'] == "REJECTED", f"Test C Failed: 404 WHO page MUST BE REJECTED, got {res_c['decision']}"
    print("   -> PASSED: 404 WHO URL correctly rejected by hard verification gate.\n")

    # TEST D: User provided invalid text instead of URL ("WHO Guidelines 2026")
    print("📌 TEST D: Plain text in URL field ('WHO Guidelines 2026')")
    res_d = who_verifier.verify_who_source(
        raw_url="WHO Guidelines 2026",
        user_source_name="WHO",
        clinical_entity="Hepatitis A",
        evidence_type="Clinical Guideline",
        evidence_text="Some text"
    )
    print(f"   HTTP Status: {res_d['http_status']}, Decision: {res_d['decision']}")
    print(f"   Rejection Reasons: {res_d['rejection_reasons']}")
    assert res_d['decision'] == "REJECTED", "Test D Failed: Plain text in URL field was not rejected!"
    assert any("Invalid Source URL" in r for r in res_d['rejection_reasons']), "Test D Failed: Missing Invalid Source URL reason"
    print("   -> PASSED: Plain text URL correctly rejected.\n")

    # TEST E: Real WHO page (Malaria) submitted for Hepatitis A candidate (Unrelated)
    print("📌 TEST E: Real WHO Malaria page submitted for Hepatitis A candidate")
    res_e = who_verifier.verify_who_source(
        raw_url="https://www.who.int/news-room/fact-sheets/detail/malaria",
        user_source_name="WHO",
        clinical_entity="Hepatitis A",
        evidence_type="Clinical Guideline",
        evidence_text="Malaria is a life-threatening disease caused by parasites transmitted to people through mosquitoes."
    )
    print(f"   Domain Verified: {res_e['who_domain_verified']}, Clinical Relevance: {res_e['clinical_relevance_score']}/100")
    print(f"   Decision: {res_e['decision']}, Rejection Reasons: {res_e['rejection_reasons']}")
    assert res_e['decision'] == "REJECTED", f"Test E Failed: Unrelated WHO page should be REJECTED, got {res_e['decision']}"
    print("   -> PASSED: Unrelated WHO page rejected as supporting evidence due to low clinical relevance.\n")

    # TEST F: Integration via SourceVerifier
    print("📌 TEST F: SourceVerifier integration test")
    res_f = verifier.evaluate_full_candidate(
        raw_source_url="https://www.who.int/news-room/fact-sheets/detail/hepatitis-a",
        text="Hepatitis A infection causing fever and jaundice.",
        clinical_entity="Hepatitis A",
        user_source_name="WHO"
    )
    print(f"   Decision: {res_f['decision']}, TrustRank: {res_f['final_trust_score']}/100")
    assert res_f['decision'] == "VERIFIED", f"Test F Failed: Expected VERIFIED, got {res_f['decision']}"
    print("   -> PASSED: SourceVerifier integration clean.\n")

    print("==================================================")
    print("ALL REAL WHO VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    run_who_real_tests()
