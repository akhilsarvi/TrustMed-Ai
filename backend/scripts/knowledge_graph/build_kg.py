from pathlib import Path

from kg.builder import MedicalKGBuilder

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "symptoms" / "DiseaseAndSymptoms.csv"

if __name__ == "__main__":
    builder = MedicalKGBuilder()
    builder.create_constraints()
    builder.build_from_csv(str(CSV_PATH))
    builder.close()