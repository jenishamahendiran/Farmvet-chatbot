import os
import time
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from google import genai
from google.genai import types
from chatbot_config import SYSTEM_PROMPT

load_dotenv()

app = Flask(__name__)
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY is not set in .env")

client = genai.Client(api_key=api_key)
MODEL = "gemini-3.1-flash-lite"

def generate_reply(history):
    contents = [
        types.Content(role=item["role"], parts=[types.Part.from_text(text=item["text"])])
        for item in history
    ]
    last_error = None

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.4,
                    max_output_tokens=700,
                ),
            )
            text = (response.text or "").strip()
            if text:
                return text
            raise RuntimeError("Empty response from Gemini.")
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()
            retryable = any(
                key in message
                for key in ("429", "rate limit", "quota", "resource exhausted", "timeout", "503", "500")
            )
            if not retryable or attempt == 2:
                break
            time.sleep(2 ** attempt)

    message = str(last_error).lower() if last_error else ""
    if any(key in message for key in ("429", "rate limit", "quota", "resource exhausted")):
        raise RuntimeError("The Gemini API quota or rate limit was reached. Please wait a moment and try again.")
    raise RuntimeError("The chatbot could not get a response right now. Please try again.")

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    history = data.get("history", [])
    if not isinstance(history, list) or not history:
        return jsonify({"error": "Please enter a question."}), 400

    clean_history = []
    for item in history[-20:]:
        if isinstance(item, dict) and item.get("role") in {"user", "model"} and item.get("text"):
            clean_history.append({
                "role": item["role"],
                "text": str(item["text"])[:6000],
            })

    if not clean_history or clean_history[-1]["role"] != "user":
        return jsonify({"error": "Please enter a question."}), 400

    try:
        reply = generate_reply(clean_history)
        return jsonify({"reply": reply})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 429 if "quota" in str(exc).lower() else 503

if __name__ == "__main__":
    app.run(debug=True)
