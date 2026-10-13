try:
    from google import genai as google_genai
except ImportError:
    google_genai = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError


class MedicalGenerator:

    def __init__(self, api_key, model_name="gemini-3.6-flash", timeout_seconds=15):
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.client = None

        if google_genai is not None:
            self.client = google_genai.Client(api_key=api_key)
            return

        if genai is None:
            raise ImportError(
                "Neither google.genai nor google.generativeai is installed. "
                "Install the Google AI SDK from requirements.txt."
            )

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    def _generate_text(self, prompt):
        if self.client is not None:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            return response.text

        response = self.model.generate_content(prompt)
        return response.text

    def generate(self, disease, drugs, evidence):
        evidence_text = "\n".join([e["text"] for e in evidence[:3]])

        prompt = f"""
You are a medical assistant.

ONLY use the provided evidence.
DO NOT hallucinate.

Disease: {disease}

Drugs: {', '.join(drugs) if drugs else "No confirmed drugs available"}

Evidence:
{evidence_text}

Generate:
1. Brief explanation of disease
2. Recommended treatment
3. Safety note if uncertainty exists
"""

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._generate_text, prompt)
            try:
                return future.result(timeout=self.timeout_seconds)
            except FutureTimeoutError as exc:
                raise TimeoutError(
                    "The medical model took too long to respond. Please retry with a shorter symptom list or check the API quota."
                ) from exc