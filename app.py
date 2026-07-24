from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, flash, send_file
import os
import json

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
import time

# Cache-busting: bump this automatically on every server restart so
# templates' `?v=` query param forces browsers to fetch the latest JS/CSS.
app.config["ASSET_VERSION"] = str(int(time.time()))

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


@app.route('/api/geocode', methods=['GET'])
def api_geocode():
    """
    Server-side proxy for Nominatim (OpenStreetMap) geocoding.

    Calling Nominatim directly from browser JS is unreliable: their usage
    policy requires a proper identifying User-Agent header, which browser
    fetch() cannot set (the browser overrides it), so many client-side
    requests get silently blocked or rate-limited. Proxying through the
    backend lets us set a real User-Agent and see the actual error if one
    occurs, instead of a mysterious client-side failure.
    """
    import requests

    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "No location query provided."}), 400

    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"format": "json", "limit": 1, "q": query},
            headers={"User-Agent": "VeriMedAI-Hackathon-Project/1.0 (educational project)"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return jsonify({"error": f'Could not find "{query}".'}), 404

        return jsonify({"lat": float(results[0]["lat"]), "lon": float(results[0]["lon"])})

    except requests.exceptions.RequestException as e:
        app.logger.error(f"[api_geocode] Nominatim request failed: {e}")
        return jsonify({"error": "Location lookup service is unavailable right now."}), 502


@app.route('/api/nearby_hospitals', methods=['GET'])
def api_nearby_hospitals():
    """
    Server-side proxy for Overpass API (OpenStreetMap) hospital/clinic search.
    Same rationale as api_geocode -- avoids client-side CORS/rate-limit
    issues and gives us real server-side error logging.
    """
    import requests
    import math

    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
    except (TypeError, ValueError):
        return jsonify({"error": "Valid lat/lon parameters are required."}), 400

    overpass_query = f"""
        [out:json][timeout:25];
        (
          node["amenity"="hospital"](around:6000,{lat},{lon});
          way["amenity"="hospital"](around:6000,{lat},{lon});
          node["amenity"="clinic"](around:6000,{lat},{lon});
          way["amenity"="clinic"](around:6000,{lat},{lon});
        );
        out center 40;
    """

    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": overpass_query},
            headers={"User-Agent": "VeriMedAI-Hackathon-Project/1.0 (educational project)"},
            timeout=25,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except requests.exceptions.RequestException as e:
        app.logger.error(f"[api_nearby_hospitals] Overpass request failed: {e}")
        return jsonify({"error": "Hospital search service is unavailable right now."}), 502

    def haversine_km(lat1, lon1, lat2, lon2):
        R = 6371
        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        a = (math.sin(d_lat / 2) ** 2
             + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def build_address(tags):
        parts = [tags.get("addr:housenumber"), tags.get("addr:street"),
                 tags.get("addr:suburb"), tags.get("addr:city"), tags.get("addr:postcode")]
        parts = [p for p in parts if p]
        return ", ".join(parts) if parts else "Address not available"

    results = []
    for el in elements:
        tags = el.get("tags", {})
        if not tags.get("name"):
            continue
        el_lat = el.get("lat") or (el.get("center") or {}).get("lat")
        el_lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if not el_lat or not el_lon:
            continue

        results.append({
            "name": tags["name"],
            "type": "Hospital" if tags.get("amenity") == "hospital" else "Clinic",
            "address": build_address(tags),
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "lat": el_lat,
            "lon": el_lon,
            "distance_km": round(haversine_km(lat, lon, el_lat, el_lon), 1),
        })

    results.sort(key=lambda h: h["distance_km"])
    return jsonify(results[:20])


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

    try:
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

    except Exception as exc:
        app.logger.exception("Claim verification failed")
        return jsonify({
            "error": "Failed to verify claim. Please try again.",
            "explanation": "A server error occurred while processing your verification request.",
            "verdict": "Unverified",
            "confidence": 0,
            "entities": [],
            "sources": [],
            "language_processed": language,
            "ocr_used": ocr_used,
            "raw_text_detected": original_claim_text,
            "claim_text_used": claim_text,
        }), 500


@app.route('/api/verify/report', methods=['POST'])
def api_verify_report():
    """Generate a downloadable PDF for the most recent claim verification."""
    data = request.get_json(silent=True) or request.form.to_dict(flat=True) or {}

    def parse_json_field(value, default):
        if value is None or value == "":
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except Exception:
            return default

    claim_text = (data.get("claim_text") or data.get("claim_text_used") or data.get("raw_text_detected") or "").strip()
    verdict = data.get("verdict") or "Unverified"
    confidence = int(data.get("confidence") or 0)
    explanation = data.get("explanation") or ""
    entities = parse_json_field(data.get("entities"), [])
    sources = parse_json_field(data.get("sources"), [])
    method_comparison = parse_json_field(data.get("method_comparison"), None)

    if not claim_text:
        return jsonify({"error": "No claim text provided for the report."}), 400

    pdf_bytes = pdf_export.generate_verification_report_pdf(
        claim_text=claim_text,
        verdict=verdict,
        confidence=confidence,
        explanation=explanation,
        entities=entities,
        sources=sources,
        method_comparison=method_comparison,
    )

    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={"Content-Disposition": "attachment; filename=VeriMed_Claim_Verification_Report.pdf"},
    )


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