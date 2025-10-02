import os
import re
import io
import json
from flask import Flask, request, render_template, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from pydantic import BaseModel

# NLP
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize

# PDF parsing
from PyPDF2 import PdfReader

# Gemini API
from google import genai
from google.genai import types

# Garantir recursos do NLTK
nltk_data_needed = ["punkt", "stopwords", "wordnet", "omw-1.4"]
for pack in nltk_data_needed:
    try:
        nltk.data.find(pack)
    except LookupError:
        nltk.download(pack)

# Config
GEMINI_API_KEY = "AIzaSyDUa_FZA2seaCpyOb2mF-d3pXqv3eZQ5Vc"
if not GEMINI_API_KEY:
    print("⚠️  GEMINI_API_KEY não está definido. Configure antes de rodar.")

ALLOWED_EXTENSIONS = {"txt", "pdf"}

app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB

lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words("portuguese")) | set(stopwords.words("english"))

#########################
# Helpers de arquivo
#########################
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_stream):
    try:
        reader = PdfReader(file_stream)
        text = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text.append(page_text)
        return "\n".join(text)
    except Exception as e:
        raise RuntimeError(f"Erro ao processar PDF: {e}")

def extract_text_from_txt(file_stream):
    try:
        data = file_stream.read()
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("latin-1")
    except Exception as e:
        raise RuntimeError(f"Erro ao processar TXT: {e}")

#########################
# Pré-processamento
#########################
def preprocess_text(text):
    if not text:
        return {"clean_text": "", "tokens": []}

    t = text.lower()
    t = re.sub(r"\S+@\S+", " ", t)
    t = re.sub(r"https?://\S+|www\.\S+", " ", t)
    t = re.sub(r"[^a-zãâáàêéíóôõúüçñ\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()

    tokens = word_tokenize(t, language="portuguese")
    tokens_filtered = [tok for tok in tokens if tok not in stop_words and len(tok) > 1]
    tokens_lem = [lemmatizer.lemmatize(tok) for tok in tokens_filtered]

    clean_text = " ".join(tokens_lem)
    return {"clean_text": clean_text, "tokens": tokens_lem}

#########################
# Chamada ao Gemini
#########################

class Resposta(BaseModel):
    category: str
    confidence: float
    rationale: str
    suggested_response: str


def call_gemini_classify_and_respond(original_text, preprocessed_text):
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY não configurada"}

    client = genai.Client(api_key=GEMINI_API_KEY)

    system_prompt = (
        "Você é um assistente que classifica emails em duas categorias: "
        "'Produtivo' (requere ação ou resposta específica) ou 'Improdutivo' (não precisa de ação imediata). "
        "Responda em JSON válido com as chaves: category, confidence (0-1), rationale (uma frase), suggested_response (texto de resposta)."
    )

    user_prompt = f"""
Texto original do email:
-----
{original_text}
-----

Texto pré-processado:
-----
{preprocessed_text}
-----

Classifique apenas em 'Produtivo' ou 'Improdutivo'. 
Dê uma confiança aproximada (ex: 0.85). 
Gere uma resposta automática curta, clara e profissional em português.
Responda SOMENTE em JSON válido.
"""

    try:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=Resposta,
                temperature=0.0,
                max_output_tokens=2048,
            ),
        )

        avaliacao_email: Resposta = resp.parsed

        return {
            "suggested_response": avaliacao_email.suggested_response,
            "category": avaliacao_email.category
        }

    except Exception as e:
        return {"error": f"Erro na chamada Gemini: {e}"}

#########################
# Rotas
#########################
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "gemini_enabled": bool(GEMINI_API_KEY)}), 200

@app.route("/", methods=["GET"])
def index():
    return render_template('index.html')
@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        original_text = ""

        if request.is_json:
            body = request.get_json()
            if "text" in body and body["text"]:
                original_text = body["text"]

        if not original_text:
            if "text" in request.form and request.form["text"].strip():
                original_text = request.form["text"]

        if not original_text and "file" in request.files:
            f = request.files["file"]
            filename = secure_filename(f.filename)
            if filename == "":
                return jsonify({"error": "Arquivo vazio"}), 400
            if not allowed_file(filename):
                return jsonify({"error": "Extensão não permitida"}), 400

            ext = filename.rsplit(".", 1)[1].lower()
            f_stream = io.BytesIO(f.read())
            f_stream.seek(0)
            if ext == "pdf":
                original_text = extract_text_from_pdf(f_stream)
            else:
                f_stream.seek(0)
                original_text = extract_text_from_txt(f_stream)

        if not original_text:
            return jsonify({"error": "Nenhum texto ou arquivo recebido"}), 400

        pre = preprocess_text(original_text)
        ai_result = call_gemini_classify_and_respond(original_text, pre["clean_text"])

        return jsonify({
            "original_text_snippet": original_text[:300],
            "preprocessed": pre,
            "classification": ai_result
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
