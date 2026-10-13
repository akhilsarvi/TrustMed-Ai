import json
import re

try:
    from google import genai as google_genai
except ImportError:
    google_genai = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None


class Q2Evaluator:
    """Question-generation evaluation for evidence-grounded answers."""

    def __init__(self, api_key, model_name="gemini-3.6-flash"):
        if not api_key or api_key.startswith("YOUR_"):
            raise ValueError("A valid GEMINI_API_KEY is required for full Q2")

        self.model_name = model_name
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

    def _generate(self, prompt):
        try:
            if self.client is not None:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )
                return response.text.strip() if response and response.text else ""

            response = self.model.generate_content(prompt)
            return response.text.strip() if response and response.text else ""
        except Exception as e:
            return ""


    @staticmethod
    def _parse_questions(text):
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            raise ValueError("Q2 question generation did not return a JSON list")
        questions = json.loads(match.group(0))
        if not isinstance(questions, list):
            raise ValueError("Q2 questions must be a JSON list")
        return [str(question).strip() for question in questions if str(question).strip()]

    @staticmethod
    def _parse_score(text):
        match = re.search(r"(?:score|entailment)\s*[:=]\s*(0(?:\.\d+)?|1(?:\.0+)?)", text.lower())
        if not match:
            raise ValueError("Q2 judge did not return a score")
        return max(0.0, min(1.0, float(match.group(1))))

    def score(self, answer, evidence, max_questions=3):
        if not answer or not evidence:
            return {"score": 0.0, "questions": [], "question_scores": []}

        questions_text = self._generate(
            """Create up to {max_questions} answerable factual questions from this answer.
Return only a JSON array of question strings. Do not add markdown.

Answer:
{answer}""".format(max_questions=max_questions, answer=answer)
        )
        questions = self._parse_questions(questions_text)[:max_questions]
        if not questions:
            return {"score": 0.0, "questions": [], "question_scores": []}

        context = evidence[:12000]
        scores = []
        for question in questions:
            judge_text = self._generate(
                """Answer the question using only the evidence, then compare that answer
with the candidate answer. Return exactly one line in this format:
score: <number from 0 to 1>

Question: {question}
Candidate answer: {answer}
Evidence:
{context}""".format(question=question, answer=answer, context=context)
            )
            scores.append(self._parse_score(judge_text))

        return {
            "score": sum(scores) / len(scores),
            "questions": questions,
            "question_scores": scores,
        }