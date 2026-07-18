from flask import Flask, render_template, request, jsonify
import json
import os

# Placeholder imports matching your engineering pipeline
# from verify_v2 import verify_claim
# from health_passport import generate_qr_code

app = Flask(__name__)
app.secret_key = "verimed_secure_session_key"

# --- PAGE ROUTING ---

@app.route('/')
def home():
    # Home/Dashboard with overview metrics
    stats = {"total_checked": 142, "true_count": 58, "false_count": 64, "misleading_count": 20}
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
    claim_text = request.form.get('claim', '')
    language = request.form.get('language', 'en')
    
    # Handle Image Upload for OCR processing
    if 'image' in request.files and request.files['image'].filename != '':
        image_file = request.files['image']
        # text_extracted = easyocr_instance.readtext(image_file.read())
        claim_text = "Extracted text from uploaded screenshot sample" 

    # Mock response demonstrating architecture values
    result = {
        "verdict": "False",
        "confidence": 94,
        "explanation": "This claim contradicts verified clinical trials and systemic data published by the WHO and CDC. There is no empirical medical evidence supporting this mechanism.",
        "entities": [
            {"text": "Garlic tea", "label": "Treatment"},
            {"text": "COVID-19", "label": "Disease_disorder"}
        ],
        "sources": ["WHO Fact Sheet 2024", "CDC Viral Pathogen Review", "PubMed Central PMC71123"],
        "language_processed": language
    }
    
    return jsonify(result)

@app.route('/api/predict_spread', methods=['POST'])
def api_predict_spread():
    """Simulates GNN (GAT) Network Spread Risk Modeling"""
    claim = request.json.get('claim', '')
    
    # Simulating structural graph risk evaluation
    graph_data = {
        "virality_score": 87,
        "risk_level": "High Risk",
        "predicted_nodes_reached": 14200,
        "time_to_peak_hours": 12,
        "network_hubs_vulnerable": ["WhatsApp Forwards Cluster A", "Public FB Groups"]
    }
    return jsonify(graph_data)

if __name__ == '__main__':
    app.run(debug=True, port=5000)