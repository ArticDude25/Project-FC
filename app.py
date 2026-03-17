from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from groq import Groq
import json
import base64
import re
import os

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────────
# PASTE YOUR GROQ API KEY HERE
# ─────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")  # ← replace

client = Groq(api_key=GROQ_API_KEY)

MODEL        = "llama-3.3-70b-versatile"
VISION_MODEL = "llama-3.2-90b-vision-preview"

# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """
You are VeriNova, India's most advanced AI fact-checking agent. You specialize
in detecting fake news, misinformation, and propaganda spreading through
WhatsApp forwards and Instagram Reels across India.

You understand and can fact-check content in ALL 22 official Indian languages:
Hindi, Bengali, Telugu, Marathi, Tamil, Urdu, Gujarati, Kannada, Odia,
Malayalam, Punjabi, Assamese, Maithili, Santali, Kashmiri, Nepali, Sindhi,
Konkani, Dogri, Manipuri, Bodo, Sanskrit as well as Hinglish.

Detect the language of the input and respond in that same language
for summary_local, debunk_comment, and forward_warning fields.
Always keep reasoning and what_actually_happened in English.

Respond ONLY with a valid JSON object in this exact format
(no extra text, no markdown, no backticks):

{
  "detected_language": "<language name>",
  "extracted_claim": "<the main claim>",
  "verdict": "FAKE" or "REAL" or "MISLEADING" or "SATIRE" or "UNVERIFIED" or "PROPAGANDA",
  "verdict_local": "<verdict in detected language>",
  "confidence": <0-100>,
  "summary": "<one sentence in English>",
  "summary_local": "<same in detected language>",
  "reasoning": ["<reason 1>", "<reason 2>", "<reason 3>"],
  "manipulation_tactics": ["<tactic 1>", "<tactic 2>"],
  "sources": ["<source 1>", "<source 2>"],
  "what_actually_happened": "<real story in English>",
  "recirculation_warning": true or false,
  "recirculation_note": "<explanation or empty string>",
  "debunk_comment": "<comment in detected language, max 200 chars>",
  "debunk_comment_english": "<same in English>",
  "forward_warning": "<warning in detected language>"
}

Rules:
- Be factual, accurate, and unbiased
- Apply deep Indian political, cultural, historical knowledge
- For Instagram Reels: focus on VIDEO content not caption
- Always provide 2+ credible sources
- Respond ONLY with JSON. Nothing else.
"""

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def call_groq(messages):
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=1500,
        temperature=0.2
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    return json.loads(raw)


def call_groq_vision(image_file, text_prompt):
    image_data   = image_file.read()
    base64_image = base64.standard_b64encode(image_data).decode("utf-8")
    media_type   = image_file.content_type or "image/jpeg"

    response = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{base64_image}"}},
                    {"type": "text", "text": text_prompt}
                ]
            }
        ],
        max_tokens=1500,
        temperature=0.2
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    return json.loads(raw)


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/check/whatsapp", methods=["POST"])
def check_whatsapp():
    message_text = request.form.get("message", "").strip()
    image_file   = request.files.get("image")

    if not message_text and not image_file:
        return jsonify({"error": "Please provide a screenshot or message text."}), 400

    try:
        if image_file:
            prompt = "This is a WhatsApp forward screenshot. Extract the message and fact-check it."
            if message_text:
                prompt += f"\n\nUser also provided: {message_text}"
            result = call_groq_vision(image_file, prompt)
        else:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": f"Fact-check this WhatsApp forward:\n\n{message_text}"}
            ]
            result = call_groq(messages)
        return jsonify(result)

    except json.JSONDecodeError:
        return jsonify({"error": "AI returned unexpected response. Try again."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/check/reel", methods=["POST"])
def check_reel():
    claim_text   = request.form.get("claim", "").strip()
    context_text = request.form.get("context", "").strip()
    image_file   = request.files.get("image")

    if not claim_text and not image_file:
        return jsonify({"error": "Please upload a screenshot or describe the claim."}), 400

    try:
        if image_file:
            prompt = (
                "This is an Instagram Reel screenshot. "
                "Read ALL visible on-screen text and subtitles — NOT just the caption. "
                "Caption is often clickbait. Focus on what the VIDEO claims."
            )
            if claim_text:
                prompt += f"\n\nUser says reel claims: {claim_text}"
            if context_text:
                prompt += f"\n\nContext: {context_text}"
            result = call_groq_vision(image_file, prompt)
        else:
            full = f"Instagram Reel claim:\n{claim_text}"
            if context_text:
                full += f"\n\nContext: {context_text}"
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": f"Fact-check this Instagram Reel:\n\n{full}"}
            ]
            result = call_groq(messages)
        return jsonify(result)

    except json.JSONDecodeError:
        return jsonify({"error": "AI returned unexpected response. Try again."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("VeriNova - India's Fact Checker")
    print("Powered by Groq + LLaMA 3.3 70B")
    print("Running at http://localhost:5000")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)