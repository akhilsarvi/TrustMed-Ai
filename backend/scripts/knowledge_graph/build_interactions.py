from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kg.interaction_builder import InteractionBuilder

CSV_PATH = PROJECT_ROOT / "data" / "raw" / "drugs" / "db_drug_interactions.csv"

if __name__ == "__main__":
    builder = InteractionBuilder()
    builder.build_from_csv(str(CSV_PATH))
    builder.close()