from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, flash, send_file
import os

from flask_login import LoginManager, login_user, logout_user, login_required, current_user

from verify_v2 import verify_claim
import db
import health_passport as hp
import ocr_utils
import spread_predictor
import translate_utils
import auth
import pdf_export
import sys, os
PROJECT_ROOT = os.path.dirname(__file__)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from gnn.gnn_predict import predict_spread
from gnn.visualization_graph import generate_visualization_graph
from comparison import compute_method_comparison

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access your Health Passport."


@login_manager.user_loader
def load_user(user_id):
    return auth.get_user_by_id(user_id)


# Make sure tables exist before anything else runs
db.init_db()
hp.init_passport_table()
auth.init_users_table()

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
@login_required
def passport():
    return render_template('passport.html', user=current_user)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('passport'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not name or not email or not password:
            flash("Please fill in all fields.", "error")
            return render_template('register.html')

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template('register.html')

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template('register.html')

        user = auth.create_user(name, email, password)
        if user is None:
            flash("An account with that email already exists. Try logging in instead.", "error")
            return render_template('register.html')

        login_user(user)
        return redirect(url_for('passport'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('passport'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        user = auth.verify_login(email, password)
        if user is None:
            flash("Incorrect email or password.", "error")
            return render_template('login.html')

        login_user(user)
        next_page = request.args.get('next')
        return redirect(next_page or url_for('passport'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/emergency-help')
def emergency_help():
    return render_template('emergency_help.html')


@app.route('/emergency/<share_token>')
def emergency_view(share_token):
    """
    Public, read-only emergency view -- this is what the QR code opens.
    No login required, intentionally shows only emergency-relevant fields.
    """
    passport_data = hp.get_passport_by_token(share_token)
    if not passport_data:
        return render_template('emergency_view.html', passport=None), 404

    surgeries = hp.get_surgeries(passport_data['user_id'])
    vaccinations = hp.get_vaccinations(passport_data['user_id'])
    return render_template('emergency_view.html', passport=passport_data, surgeries=surgeries, vaccinations=vaccinations)

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

        try:
            extracted_text = ocr_utils.extract_text_from_image(image_bytes, language_code=language)
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

    # Translate non-English input into English before running the NER/RAG/LLM
    # pipeline (which operates in English). This now applies to both typed
    # and OCR-extracted text.
    original_claim_text = claim_text
    if language != "en":
        claim_text = translate_utils.translate_to_english(claim_text, language)

    result = verify_claim(claim_text)

    # Persist to history in English (keeps retrieval/history consistent)
    db.save_result(claim_text, result)

    # Translate the explanation back into the user's selected language for display
    explanation_for_display = result.get("explanation", "")
    if language != "en":
        explanation_for_display = translate_utils.translate_from_english(explanation_for_display, language)

    # Compute the GNN spread-risk prediction and the 3-method comparison.
    # This reuses the verdict/confidence/entities already computed above --
    # no second LLM call, just fast local scoring.
    spread_result = predict_spread(
        claim_text=claim_text,
        verdict=result.get("verdict", "Unverified"),
        confidence=result.get("confidence", 0),
        entities=result.get("entities", []),
    )
    method_comparison = compute_method_comparison(claim_text, result, spread_result)

    response = {
        "verdict": result.get("verdict"),
        "confidence": result.get("confidence"),
        "explanation": explanation_for_display,
        "entities": result.get("entities", []),
        "sources": result.get("sources", []),
        "language_processed": language,
        "ocr_used": ocr_used,
        "raw_text_detected": original_claim_text,
        "claim_text_used": claim_text,
        "spread_prediction": spread_result,
        "method_comparison": method_comparison,
    }
    return jsonify(response)


@app.route('/api/tts', methods=['POST'])
def api_tts():
    """
    Server-side text-to-speech fallback using gTTS.

    The browser's built-in speech synthesis depends on voices installed on
    the user's device -- many devices don't have Hindi/Marathi voices
    installed, which silently falls back to English. This endpoint
    generates real audio in the requested language regardless of what's
    installed locally.
    """
    from gtts import gTTS
    import io

    data = request.get_json(force=True) or {}
    text = data.get('text', '').strip()
    lang = data.get('lang', 'en')

    if not text:
        return jsonify({"error": "No text provided."}), 400

    # gTTS language codes -- Marathi isn't supported by gTTS, so we fall
    # back to Hindi audio for Marathi text (closer than English, and this
    # is only reached when no local Marathi voice exists anyway).
    gtts_lang = {"en": "en", "hi": "hi", "mr": "hi"}.get(lang, "en")

    try:
        tts = gTTS(text=text, lang=gtts_lang)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return Response(buf.read(), mimetype='audio/mpeg')
    except Exception as e:
        return jsonify({"error": f"TTS generation failed: {e}"}), 500


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
    Spread Risk Estimation.
    Primary path: a real trained Graph Attention Network (Phase 6). See
    gnn/ for the model, training script, and inference code.
    Fallback path: if the trained model can't load or inference throws for
    any reason, we fall back to spread_predictor.py's explainable heuristic
    scorer (real graph-centrality + knowledge-base-similarity signals, not
    a placeholder) so this endpoint never hard-crashes and never silently
    returns nothing.
    """
    claim = (request.json or {}).get('claim', '').strip()
    if not claim:
        return jsonify({"error": "No claim provided."}), 400

    # Run the same verification pipeline used by /api/verify so the GNN's
    # risk features (verdict, confidence, entities) are grounded in real
    # evidence, not guessed independently.
    verification = verify_claim(claim)
    graph_data = predict_spread(
        claim_text=claim,
        verdict=verification.get("verdict", "Unverified"),
        confidence=verification.get("confidence", 0),
        entities=verification.get("entities", []),
    )

    # Node-by-node visualization -- a smaller, legible graph with the SAME
    # epidemic simulation logic used to train the model, run live on this
    # claim's actual risk profile. Wrapped defensively so a visualization
    # bug never breaks the numeric prediction above.
    try:
        graph_data["visualization"] = generate_visualization_graph(
            claim_text=claim,
            verdict=verification.get("verdict", "Unverified"),
            confidence=verification.get("confidence", 0),
            entities=verification.get("entities", []),
        )
    except Exception as e:
        print(f"[api_predict_spread] Visualization graph failed: {e}")
        graph_data["visualization"] = None

    return jsonify(graph_data)


@app.route('/api/passport', methods=['GET', 'POST'])
@login_required
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
        hp.save_passport(int(current_user.id), data)
        return jsonify({"status": "saved"})

    passport_data = hp.get_passport(int(current_user.id))
    if not passport_data:
        return jsonify(None)
    return jsonify(passport_data)


@app.route('/api/passport/qr', methods=['GET'])
@login_required
def api_passport_qr():
    passport_data = hp.get_passport(int(current_user.id))
    if not passport_data:
        return jsonify({"error": "No passport saved yet."}), 404
    png_bytes = hp.generate_qr_code(passport_data['share_token'], request.host_url)
    return Response(png_bytes, mimetype='image/png')


@app.route('/api/passport/surgeries', methods=['GET', 'POST'])
@login_required
def api_surgeries():
    if request.method == 'POST':
        data = request.get_json(force=True) or {}
        hp.add_surgery(int(current_user.id), data.get('year', ''), data.get('description', ''))
        return jsonify({"status": "added"})
    return jsonify(hp.get_surgeries(int(current_user.id)))


@app.route('/api/passport/surgeries/<int:surgery_id>', methods=['DELETE'])
@login_required
def api_delete_surgery(surgery_id):
    hp.delete_surgery(int(current_user.id), surgery_id)
    return jsonify({"status": "deleted"})


@app.route('/api/passport/vaccinations', methods=['GET', 'POST'])
@login_required
def api_vaccinations():
    if request.method == 'POST':
        data = request.get_json(force=True) or {}
        hp.add_vaccination(int(current_user.id), data.get('vaccine_name', ''), data.get('month', ''), data.get('year', ''))
        return jsonify({"status": "added"})
    return jsonify(hp.get_vaccinations(int(current_user.id)))


@app.route('/api/passport/vaccinations/<int:vaccination_id>', methods=['DELETE'])
@login_required
def api_delete_vaccination(vaccination_id):
    hp.delete_vaccination(int(current_user.id), vaccination_id)
    return jsonify({"status": "deleted"})


@app.route('/api/passport/reports', methods=['GET', 'POST'])
@login_required
def api_reports():
    if request.method == 'POST':
        if 'file' not in request.files or request.files['file'].filename == '':
            return jsonify({"error": "No file provided."}), 400
        file_storage = request.files['file']
        category = request.form.get('category', 'Other')
        month = request.form.get('month', '')
        year = request.form.get('year', '')
        report = hp.save_report_file(int(current_user.id), file_storage, category, month, year)
        return jsonify(report)

    return jsonify(hp.get_reports(int(current_user.id)))


@app.route('/api/passport/reports/<int:report_id>', methods=['DELETE'])
@login_required
def api_delete_report(report_id):
    hp.delete_report(int(current_user.id), report_id)
    return jsonify({"status": "deleted"})


@app.route('/api/passport/reports/<int:report_id>/download', methods=['GET'])
@login_required
def api_download_report(report_id):
    report = hp.get_report_by_id(int(current_user.id), report_id)
    if not report or not os.path.exists(report['stored_path']):
        return jsonify({"error": "Report not found."}), 404
    return send_file(report['stored_path'], as_attachment=True, download_name=report['filename'])


@app.route('/api/passport/pdf', methods=['GET'])
@login_required
def api_passport_pdf():
    passport_data = hp.get_passport(int(current_user.id))
    if not passport_data:
        return jsonify({"error": "No passport saved yet."}), 404

    surgeries = hp.get_surgeries(int(current_user.id))
    vaccinations = hp.get_vaccinations(int(current_user.id))
    qr_bytes = hp.generate_qr_code(passport_data['share_token'], request.host_url)

    pdf_bytes = pdf_export.generate_passport_pdf(passport_data, surgeries, vaccinations, qr_bytes)

    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={"Content-Disposition": "attachment; filename=VeriMed_Health_Passport.pdf"},
    )


if __name__ == '__main__':
    app.run(debug=True, port=5000, use_reloader=False)