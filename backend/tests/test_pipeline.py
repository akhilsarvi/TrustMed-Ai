from pipeline.full_pipeline import MedicalPipeline

if __name__ == "__main__":
    pipeline = MedicalPipeline()

    symptoms = ["itching", "nodal skin eruptions", "dischromic patches"]



    pipeline.run(symptoms)

    pipeline.close()