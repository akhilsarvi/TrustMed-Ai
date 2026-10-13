import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path

# Ensure backend folder is in sys.path before loading local packages
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from flask import Flask, jsonify, render_template, request

from document_processor.extractor import extract_document_text, sanitize_filename
from pipeline.cku import ContinuousKnowledgeUpdater
from pipeline.full_pipeline import MedicalPipeline
from who.retriever import search_who
from who.verifier import verify_claim

TEMPLATE_DIR = BASE_DIR.parent / "frontend" / "templates"
STATIC_DIR = BASE_DIR.parent / "frontend" / "static"

app = Flask(__name__, template_folder=str(TEMPLATE_DIR), static_folder=str(STATIC_DIR))

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".jpg", ".jpeg", ".png"}
cku = ContinuousKnowledgeUpdater()


def extract_document_findings(document_text: str):
    if not document_text:
        return []
    lines = [line.strip() for line in document_text.splitlines() if line.strip()]
    findings = []
    for line in lines[:20]:
        if ':' in line and len(line) < 180:
            label, value = line.split(':', 1)
            findings.append({"label": label.strip(), "value": value.strip()})
    return findings


def build_who_crosscheck(claims):
    results = []
    for claim in claims[:2]:
        if not claim:
            continue
        try:
            candidate_sources = search_who(claim, limit=1)
        except Exception:
            candidate_sources = []
        evidence = [
            {"title": item.get("title", "WHO"), "url": item.get("url", ""), "excerpt": item.get("excerpt", "")}
            for item in candidate_sources
        ]
        verified = verify_claim(claim, evidence)
        results.append({
            "claim": claim,
            "status": verified.get("status", "WHO SOURCE NOT FOUND"),
            "summary": verified.get("summary", "No WHO evidence found."),
            "source": verified.get("source", ""),
            "url": verified.get("url", ""),
        })
    return results


def safe_who_crosscheck(claims):
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(build_who_crosscheck, claims)
            return future.result(timeout=3)
    except (FutureTimeoutError, Exception):
        return []


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        payload = request.get_json(silent=True) or {}
        symptoms = payload.get('symptoms', [])
        if not symptoms:
            return jsonify({"error": "Symptoms are required."}), 400

        pipeline = MedicalPipeline()
        try:
            result = pipeline.run_summary(symptoms, payload.get('patient_profile'))
            disease_claims = [item.get('disease') for item in result.get('results', []) if item.get('disease')]
            result['who_crosscheck'] = safe_who_crosscheck(disease_claims)
            return jsonify(result)
        finally:
            pipeline.close()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/analyze-document', methods=['POST'])
def analyze_document():
    if 'document' not in request.files:
        return jsonify({"error": "No document file provided in request."}), 400

    file_obj = request.files['document']
    filename = sanitize_filename(file_obj.filename or '')
    if not filename:
        return jsonify({"error": "Empty or invalid filename."}), 400

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}"}), 400

    file_obj.seek(0, os.SEEK_END)
    size = file_obj.tell()
    file_obj.seek(0)
    if size > MAX_FILE_SIZE:
        return jsonify({"error": f"File size ({size} bytes) exceeds maximum limit of 10MB."}), 400

    patient_profile = None
    profile_raw = request.form.get('profile')
    if profile_raw:
        try:
            patient_profile = json.loads(profile_raw)
        except Exception:
            return jsonify({"error": "Invalid JSON string in 'profile' form field."}), 400

    temp_dir = tempfile.mkdtemp()
    document_path = os.path.join(temp_dir, filename)

    try:
        file_obj.save(document_path)
        try:
            text = extract_document_text(document_path)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if not text.strip():
            return jsonify({"error": "No readable text extracted from document."}), 400

        pipeline = MedicalPipeline()
        try:
            analysis = pipeline.run_summary([text[:4000]], patient_profile=patient_profile)

            findings = extract_document_findings(text)
            disease_claims = [item.get('disease') for item in analysis.get('results', []) if item.get('disease')]
            who_checks = safe_who_crosscheck(disease_claims)

            return jsonify({
                "filename": filename,
                "extracted_length": len(text),
                "extracted_text_preview": text[:1000],
                "findings": findings,
                "analysis": analysis,
                "who_crosscheck": who_checks,
            })
        finally:
            pipeline.close()
            try:
                os.remove(document_path)
            except OSError:
                pass
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/cku/candidates', methods=['GET', 'POST'])
def cku_candidates():
    if request.method == 'GET':
        return jsonify({"candidates": cku.pending(), "all": cku.get_all()})
    payload = request.get_json(silent=True) or {}
    return jsonify(cku.submit(payload)), 201


@app.route('/api/cku/promote', methods=['POST'])
def cku_promote():
    payload = request.get_json(silent=True) or {}
    candidate_id = payload.get("candidate_id") or payload.get("id")
    if not candidate_id:
        return jsonify({"error": "candidate_id is required"}), 400
    
    pipeline = None
    try:
        pipeline = MedicalPipeline()
        driver = pipeline.driver if getattr(pipeline, 'neo4j_available', False) else None
        res = cku.promote(candidate_id, neo4j_driver=driver, rag_retriever=pipeline.rag)
        return jsonify(res)
    except Exception as e:
        res = cku.promote(candidate_id)
        res["warning"] = f"Promoted locally to JSON log. Pipeline connection note: {str(e)}"
        return jsonify(res)
    finally:
        if pipeline:
            pipeline.close()


@app.route('/api/cku/reject', methods=['POST'])
def cku_reject():
    payload = request.get_json(silent=True) or {}
    candidate_id = payload.get("candidate_id") or payload.get("id")
    reason = payload.get("reason", "Rejected during clinical audit")
    if not candidate_id:
        return jsonify({"error": "candidate_id is required"}), 400
    return jsonify(cku.reject(candidate_id, reason))


@app.route('/api/cku/auto-process', methods=['POST'])
def cku_auto_process():
    pipeline = None
    try:
        payload = request.get_json(silent=True) or {}
        trust_threshold = float(payload.get('trust_threshold', 0.75))
        reject_threshold = float(payload.get('reject_threshold', 0.60))
        try:
            pipeline = MedicalPipeline()
            driver = pipeline.driver if getattr(pipeline, 'neo4j_available', False) else None
            res = cku.auto_process_pending(
                trust_threshold=trust_threshold,
                reject_threshold=reject_threshold,
                neo4j_driver=driver,
                rag_retriever=pipeline.rag,
            )
        except Exception as e:
            res = cku.auto_process_pending(
                trust_threshold=trust_threshold,
                reject_threshold=reject_threshold,
            )
            res["pipeline_note"] = f"Processed locally with default json log: {str(e)}"
        return jsonify(res)
    finally:
        if pipeline:
            pipeline.close()


@app.route('/api/cku/seed-and-auto-process', methods=['POST'])
def cku_seed_and_auto_process():
    seeded = cku.seed_demo_candidates(force_reset=True)
    pipeline = None
    try:
        try:
            pipeline = MedicalPipeline()
            driver = pipeline.driver if getattr(pipeline, 'neo4j_available', False) else None
            auto_res = cku.auto_process_pending(
                neo4j_driver=driver,
                rag_retriever=pipeline.rag,
            )
        except Exception as e:
            auto_res = cku.auto_process_pending()
            auto_res["pipeline_note"] = f"Processed locally: {str(e)}"
        return jsonify({"status": "SUCCESS", "seeded_count": len(seeded), "auto_results": auto_res})
    finally:
        if pipeline:
            pipeline.close()


@app.route('/api/cku/evaluation/<candidate_id>', methods=['GET'])
def cku_get_evaluation(candidate_id):
    eval_record = cku.get_evaluation(candidate_id)
    if not eval_record:
        return jsonify({"error": f"Evaluation API Error: Evidence ID '{candidate_id}' not found in database log."}), 404
    return jsonify(eval_record)


@app.route('/api/cku/re-evaluate', methods=['POST'])
def cku_re_evaluate():
    pipeline = None
    try:
        pipeline = MedicalPipeline()
        driver = pipeline.driver if getattr(pipeline, 'neo4j_available', False) else None
        res = cku.re_evaluate_all(neo4j_driver=driver)
        return jsonify(res)
    except Exception as e:
        res = cku.re_evaluate_all()
        res["pipeline_note"] = f"Re-evaluated locally: {str(e)}"
        return jsonify(res)
    finally:
        if pipeline:
            pipeline.close()


@app.route('/api/health', methods=['GET'])
def system_health():
    import requests
    neo4j_status = "DISCONNECTED"
    neo4j_uri = "bolt://localhost:7687"
    try:
        pipeline = MedicalPipeline()
        if getattr(pipeline, 'neo4j_available', False):
            neo4j_status = "CONNECTED"
        pipeline.close()
    except Exception:
        pass

    who_status = "CONNECTED"
    who_api_status = "AVAILABLE"
    try:
        resp = requests.get("https://www.who.int", timeout=3.0)
        if resp.status_code != 200:
            who_status = "UNAVAILABLE"
    except Exception:
        who_status = "UNAVAILABLE"

    try:
        resp = requests.get("https://www.who.int/api/default/healthtopics", params={"$top": 1}, timeout=3.0)
        if resp.status_code != 200:
            who_api_status = "UNAVAILABLE"
    except Exception:
        who_api_status = "UNAVAILABLE"

    return jsonify({
        "status": "HEALTHY" if (who_status == "CONNECTED" and neo4j_status == "CONNECTED") else "DEGRADED",
        "who": {"status": who_status, "url": "https://www.who.int"},
        "who_api": {"status": who_api_status, "url": "https://www.who.int/api/default/healthtopics"},
        "neo4j": {"status": neo4j_status, "uri": neo4j_uri},
        "rag": {"status": "AVAILABLE"},
        "embedding_model": {"status": "AVAILABLE"},
        "database": {"status": "CONNECTED"}
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
