from flask import Flask, render_template, request, jsonify, Response
import os

from verify_v2 import verify_claim
import db
import health_passport as hp
import ocr_utils
import translate_utils

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")

# Make sure tables exist before anything else runs
db.init_db()
hp.init_passport_table()

# --- PAGE ROUTING ---

@app.route('/')
def home():
    raw_stats = db.get_stats()
    by_verdict = raw_stats.get("by_verdict", {})
    stats = {
        "total_checked": raw_stats.get("total_checked", 0),
        "true_count": by_verdict.get("True", 0),
        "false_count": by_verdict.get("False", 0),
        "misleading_count": by_verdict.get("Misleading", 0),
    }
    return render_template('index.html', stats=stats)

@app.route('/checker')
def checker():
    return render_template('checker.html')

@app.route('/predictor')
def predictor():
    return render_template('predictor.html')

@app.route('/passport')
def passport():
    return render_template('passport.html')

# --- API ENDPOINTS ---

@app.route('/api/verify', methods=['POST'])
def api_verify():
    """Handles multimodal/multilingual inputs (Text, URL, Images via OCR)"""
    claim_text = request.form.get('claim', '').strip()
    language = request.form.get('language', 'en')
    ocr_used = False

    # Handle Image Upload for OCR processing
    if 'image' in request.files and request.files['image'].filename != '':
        image_file = request.files['image']
        image_bytes = image_file.read()

        if language != 'en':
            return jsonify({
                "verdict": "Unverified",
                "confidence": 0,
                "explanation": "Screenshot OCR currently only supports English. Please select English, or paste the claim as text instead.",
                "entities": [],
                "sources": [],
                "language_processed": language,
            }), 422

        try:
            extracted_text = ocr_utils.extract_text_from_image(image_bytes)
        except Exception:
            return jsonify({
                "verdict": "Unverified",
                "confidence": 0,
                "explanation": "Something went wrong reading this image. Please try a clearer screenshot or paste the claim as text.",
                "entities": [],
                "sources": [],
                "language_processed": language,
            }), 500

        if not extracted_text:
            return jsonify({
                "verdict": "Unverified",
                "confidence": 0,
                "explanation": "Couldn't find any readable text in this image. Try a clearer or higher-resolution screenshot, or paste the claim as text.",
                "entities": [],
                "sources": [],
                "language_processed": language,
            }), 422

        claim_text = extracted_text
        ocr_used = True

    if not claim_text:
        return jsonify({"error": "No claim text provided."}), 400

    # Translate non-English TEXT claims into English before running the
    # NER/RAG/LLM pipeline (which operates in English). OCR path above is
    # already restricted to English images, so this only applies to typed
    # or voice-transcribed text in another language.
    original_claim_text = claim_text
    if language != "en" and not ocr_used:
        claim_text = translate_utils.translate_to_english(claim_text, language)

    result = verify_claim(claim_text)

    # Persist to history in English (keeps retrieval/history consistent)
    db.save_result(claim_text, result)

    # Translate the explanation back into the user's selected language for display
    explanation_for_display = result.get("explanation", "")
    if language != "en":
        explanation_for_display = translate_utils.translate_from_english(explanation_for_display, language)

    response = {
        "verdict": result.get("verdict"),
        "confidence": result.get("confidence"),
        "explanation": explanation_for_display,
        "entities": result.get("entities", []),
        "sources": result.get("sources", []),
        "language_processed": language,
        "ocr_used": ocr_used,
        "claim_text_used": claim_text if (ocr_used or language != "en") else None,
    }
    return jsonify(response)


@app.route('/api/history', methods=['GET'])
def api_history():
    limit = request.args.get('limit', default=20, type=int)
    return jsonify(db.get_history(limit=limit))


@app.route('/api/trending', methods=['GET'])
def api_trending():
    limit = request.args.get('limit', default=5, type=int)
    return jsonify(db.get_trending_verdicts(limit=limit))


@app.route('/api/predict_spread', methods=['POST'])
def api_predict_spread():
    """
    Spread Risk Modeling.
    NOTE: the real GNN/GAT layer (Phase 6) isn't built yet -- this is a
    clearly-labeled heuristic placeholder, not the trained model described
    in the pitch. Swap this out once Phase 6 lands.
    """
    claim = (request.json or {}).get('claim', '')
    if not claim.strip():
        return jsonify({"error": "No claim provided."}), 400

    graph_data = {
        "virality_score": 87,
        "risk_level": "High Risk",
        "predicted_nodes_reached": 14200,
        "time_to_peak_hours": 12,
        "network_hubs_vulnerable": ["WhatsApp Forwards Cluster A", "Public FB Groups"],
        "is_simulated": True,  # tells the frontend to label this as a placeholder
    }
    return jsonify(graph_data)


@app.route('/api/passport', methods=['GET', 'POST'])
def api_passport():
    if request.method == 'POST':
        data = request.get_json(force=True) or {}
        required_defaults = {
            "full_name": "", "blood_group": "", "date_of_birth": "",
            "allergies": "", "chronic_conditions": "", "current_medicines": "",
            "emergency_contact_name": "", "emergency_contact_phone": "",
        }
        for key, default in required_defaults.items():
            data.setdefault(key, default)
        hp.save_passport(data)
        return jsonify({"status": "saved"})

    passport_data = hp.get_passport()
    if not passport_data:
        return jsonify(None)
    return jsonify(passport_data)


@app.route('/api/passport/qr', methods=['GET'])
def api_passport_qr():
    passport_data = hp.get_passport()
    if not passport_data:
        return jsonify({"error": "No passport saved yet."}), 404
    png_bytes = hp.generate_qr_code(passport_data)
    return Response(png_bytes, mimetype='image/png')


if __name__ == '__main__':
    app.run(debug=True, port=5000, use_reloader=False)