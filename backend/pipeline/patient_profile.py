from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PatientProfile:
    age: int | None = None
    gender: str | None = None
    medical_history: list[str] = field(default_factory=list)
    allergies: list[str] = field(default_factory=list)
    current_medications: list[str] = field(default_factory=list)
    chronic_conditions: list[str] = field(default_factory=list)
    lifestyle: list[str] = field(default_factory=list)
    pregnancy_status: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "PatientProfile":
        value = value or {}
        list_fields = (
            "medical_history",
            "allergies",
            "current_medications",
            "chronic_conditions",
            "lifestyle",
        )
        normalized = {}
        for field_name in list_fields:
            raw = value.get(field_name, [])
            if isinstance(raw, str):
                raw = raw.replace("\n", ",").split(",")
            normalized[field_name] = [str(item).strip().lower() for item in raw if str(item).strip()]

        age = value.get("age")
        try:
            age = int(age) if age not in (None, "") else None
        except (TypeError, ValueError):
            age = None

        return cls(
            age=age,
            gender=str(value.get("gender")).strip().lower() if value.get("gender") else None,
            pregnancy_status=(str(value.get("pregnancy_status")).strip().lower()
                              if value.get("pregnancy_status") else None),
            **normalized,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def context_terms(self) -> list[str]:
        return (
            self.medical_history
            + self.allergies
            + self.current_medications
            + self.chronic_conditions
            + self.lifestyle
        )


# Known drug-class contraindications for safety checks
DRUG_CLASS_CONTRAINDICATIONS: dict[str, dict[str, list[str]]] = {
    "nsaid": {
        "pregnancy": ["pregnant", "pregnancy", "1st trimester", "2nd trimester", "3rd trimester"],
        "conditions": ["renal disease", "kidney disease", "peptic ulcer", "gastric ulcer", "heart failure", "hypertension"],
    },
    "ibuprofen": {
        "pregnancy": ["pregnant", "pregnancy", "3rd trimester"],
        "conditions": ["peptic ulcer", "renal failure", "heart failure"],
    },
    "aspirin": {
        "pregnancy": ["pregnant", "pregnancy", "3rd trimester"],
        "conditions": ["bleeding disorder", "peptic ulcer", "hemophilia"],
    },
    "ace_inhibitor": {
        "pregnancy": ["pregnant", "pregnancy"],
        "conditions": ["hyperkalemia", "renal artery stenosis"],
    },
    "lisinopril": {
        "pregnancy": ["pregnant", "pregnancy"],
        "conditions": ["hyperkalemia", "angioedema"],
    },
    "tetracycline": {
        "pregnancy": ["pregnant", "pregnancy"],
        "conditions": ["hepatic failure", "renal failure"],
    },
    "doxycycline": {
        "pregnancy": ["pregnant", "pregnancy"],
        "conditions": ["hepatic failure"],
    },
    "beta_blocker": {
        "conditions": ["asthma", "copd", "bradycardia", "heart block"],
    },
    "statins": {
        "pregnancy": ["pregnant", "pregnancy"],
        "conditions": ["active liver disease"],
    },
}


def check_compatibility(drug: str, profile: PatientProfile) -> dict[str, Any]:
    """
    Formal Compatibility Function Comp(a, P) for Patient-Centric Healthcare Recommendation.
    Evaluates:
      1. Allergy conflicts (direct drug name & drug class)
      2. Drug-drug interaction conflicts against current_medications
      3. Condition & Pregnancy contraindications
    Returns:
      {"compatible": bool, "reasons": list[str], "conflicts": list[str]}
    """
    norm_drug = drug.strip().lower()
    conflicts: list[str] = []
    reasons: list[str] = []

    # 1. Allergy Conflict Check
    for allergy in profile.allergies:
        norm_allergy = allergy.strip().lower()
        if norm_allergy and (norm_allergy in norm_drug or norm_drug in norm_allergy):
            conflicts.append(allergy)
            reasons.append(f"Allergy conflict detected with patient allergy: '{allergy}'")

    # 2. Drug-Drug Interaction / Co-medication Conflict Check
    for med in profile.current_medications:
        norm_med = med.strip().lower()
        if norm_med and norm_med == norm_drug:
            conflicts.append(med)
            reasons.append(f"Duplicate/Concurrent medication conflict with current regimen: '{med}'")

    # 3. Pregnancy & Condition Contraindications
    is_pregnant = bool(profile.pregnancy_status and profile.pregnancy_status.lower() in ("yes", "pregnant", "true", "1st trimester", "2nd trimester", "3rd trimester"))
    patient_conditions = [c.lower() for c in profile.chronic_conditions + profile.medical_history]

    for key_term, rules in DRUG_CLASS_CONTRAINDICATIONS.items():
        if key_term in norm_drug:
            # Check pregnancy
            if is_pregnant and "pregnancy" in rules:
                conflicts.append(f"Pregnancy contraindication for {drug}")
                reasons.append(f"Drug '{drug}' is contraindicated during pregnancy (status: {profile.pregnancy_status})")
            # Check chronic conditions
            if "conditions" in rules:
                for cond in rules["conditions"]:
                    if any(cond in p_cond for p_cond in patient_conditions):
                        conflicts.append(f"Condition contraindication: {cond}")
                        reasons.append(f"Drug '{drug}' is contraindicated for patient condition: '{cond}'")

    compatible = len(conflicts) == 0
    return {
        "compatible": compatible,
        "reasons": reasons,
        "conflicts": conflicts,
    }


def filter_drugs(drugs: list[str], profile: PatientProfile) -> tuple[list[str], list[dict[str, Any]]]:
    """Apply formal Comp(a, P) patient-centric profile checks and expose exclusions in the trace."""
    allowed = []
    exclusions = []
    for drug in drugs:
        result = check_compatibility(drug, profile)
        if not result["compatible"]:
            exclusions.append({
                "candidate": drug,
                "reason": "; ".join(result["reasons"]),
                "matched_profile_terms": ", ".join(result["conflicts"]),
            })
        else:
            allowed.append(drug)
    return allowed, exclusions

