from pipeline.query_engine import SymptomQueryEngine

if __name__ == "__main__":
    engine = SymptomQueryEngine()

    symptoms = ["cough", "cold", "fever"]

    results = engine.find_diseases(symptoms)

    print("\n🔍 Query:", symptoms)
    print("\n🧠 Results:")

    for r in results:
        print(r)

    engine.close()