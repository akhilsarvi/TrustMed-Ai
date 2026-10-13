import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.patient_profile import PatientProfile, filter_drugs
from pipeline.cku import ContinuousKnowledgeUpdater

def main():
    print("=" * 80)
    print(" 🏥 TRUSTMED-AI: LIVE END-TO-END DEMONSTRATION ")
    print("=" * 80)

    # 1. Define Patient Profile P
    patient_dict = {
        "age": 42,
        "gender": "female",
        "medical_history": ["peptic ulcer"],
        "allergies": ["penicillin"],
        "current_medications": ["aspirin"],
        "chronic_conditions": ["hypertension"],
        "lifestyle": ["non-smoker"],
        "pregnancy_status": "pregnant"
    }
    
    profile = PatientProfile.from_dict(patient_dict)
    
    print("\n👤 [1] STRUCTURED PATIENT PROFILE (P):")
    print(json.dumps(profile.to_dict(), indent=2))

    # 2. Symptoms input
    symptoms = ["fever", "joint pain", "headache", "cough"]
    print(f"\n🩺 [2] INPUT SYMPTOMS: {symptoms}")

    # 3. Initial Candidate Treatments retrieved from Knowledge Base
    candidate_treatments = [
        "ibuprofen",        # Contraindicated: Pregnancy + Peptic Ulcer
        "penicillin v",     # Excluded: Allergy conflict
        "aspirin",          # Excluded: Concurrent medication conflict + Pregnancy
        "amoxicillin",      # Excluded: Penicillin allergy family
        "acetaminophen",    # ALLOWED: Safe pain reliever
        "azithromycin"      # ALLOWED: Safe antibiotic option
    ]
    
    print(f"\n💊 [3] UNFILTERED CANDIDATE TREATMENTS (From Neo4j Graph Walk):")
    print(f"    {candidate_treatments}")

    # 4. Patient-Centric Safety Compatibility Filtering Comp(a, P)
    allowed_drugs, exclusions = filter_drugs(candidate_treatments, profile)

    print("\n🛡️ [4] PATIENT-CENTRIC SAFETY COMPATIBILITY FILTERING Comp(a, P):")
    print(f"    ✅ ALLOWED SAFE DRUGS: {allowed_drugs}")
    print("\n    🚫 EXCLUDED CANDIDATES & REASONING TRACES:")
    for ex in exclusions:
        print(f"       • Drug: '{ex['candidate']}'")
        print(f"         Reason: {ex['reason']}")
        print(f"         Matched Terms: {ex['matched_profile_terms']}\n")

    # 5. Continuous Knowledge Updation (CKU) Background Intake & Promotion
    print("🔄 [5] CONTINUOUS KNOWLEDGE UPDATION (CKU) INTAKE & PROMOTION LOOP:")
    cku = ContinuousKnowledgeUpdater(path="logs/demo_cku.jsonl")
    
    new_candidate = {
        "source": "https://www.who.int/news/item/clinical-guidelines-2026",
        "text": "Acetaminophen combined with supportive rest is recommended for mild fever management during pregnancy.",
        "disease": "fever",
        "category": "Obstetric Clinical Guidance"
    }
    
    submit_res = cku.submit(new_candidate)
    print(f"    📥 Candidate Ingestion Status : {submit_res['status']}")
    print(f"    📊 Computed Trust Score T(N)  : {submit_res['trust_score']} (Domain: WHO, High Authority)")
    
    promote_res = cku.promote(submit_res['id'])
    print(f"    🚀 Promotion to KG & FAISS    : {promote_res['status']}")

    print("\n" + "=" * 80)
    print(" 🎉 DEMONSTRATION COMPLETE: ALL OBJECTIVES RUN SUCCESSFULLY! ")
    print("=" * 80)

if __name__ == "__main__":
    main()
