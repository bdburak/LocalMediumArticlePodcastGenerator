from flask import Flask, render_template, request, session, jsonify, send_from_directory
import os
import json
import time
from ttsClass import TTS

app = Flask(__name__)
app.secret_key = "podcast-generator-secret-key"
app.config["UPLOAD_FOLDER"] = "uploads/ref_voices"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

PLACEHOLDER_DIALOG = "placaholders/LOG_dialog.json"
PLACEHOLDER_AUDIO = "placaholders/full_episode_async.wav"

tts = TTS()


def placeholder_fetch_article(url):
    time.sleep(1)
    return {
        "title": "The Future of AI in Software Development",
        "content": "Article content would be fetched here using Playwright and BeautifulSoup...",
        "url": url,
    }


def placeholder_generate_script(article_data):
    time.sleep(2)
    with open(PLACEHOLDER_DIALOG, "r", encoding="UTF-8") as f:
        return json.load(f)


def placeholder_upload_reference_audio(filename, transcript=None):
    time.sleep(0.5)
    return {"status": "uploaded", "filename": filename}


def placeholder_generate_voice_clones():
    steps = [
        "Analyzing reference audio A...",
        "Extracting voice features from Speaker A...",
        "Training voice model for Speaker A...",
        "Analyzing reference audio B...",
        "Extracting voice features from Speaker B...",
        "Training voice model for Speaker B...",
        "Voice clones generated successfully!",
    ]
    for step in steps:
        yield step
        time.sleep(1)


def placeholder_generate_podcast():
    steps = [
        "Initializing TTS engine...",
        "Synthesizing segment 1/11...",
        "Synthesizing segment 2/11...",
        "Synthesizing segment 3/11...",
        "Synthesizing segment 4/11...",
        "Synthesizing segment 5/11...",
        "Synthesizing segment 6/11...",
        "Synthesizing segment 7/11...",
        "Synthesizing segment 8/11...",
        "Synthesizing segment 9/11...",
        "Synthesizing segment 10/11...",
        "Synthesizing segment 11/11...",
        "Mixing audio tracks...",
        "Adding transitions...",
        "Finalizing podcast audio...",
        "Podcast generated successfully!",
    ]
    for step in steps:
        yield step
        time.sleep(0.8)


@app.route("/")
def index():
    if "stage" not in session:
        session["stage"] = 1
    if "dialog" not in session:
        session["dialog"] = None
    if "voice_a" not in session:
        session["voice_a"] = None
    if "voice_b" not in session:
        session["voice_b"] = None
    if "podcast_ready" not in session:
        session["podcast_ready"] = False
    return render_template("index.html", stage=session.get("stage", 1))


@app.route("/api/fetch-article", methods=["POST"])
def api_fetch_article():
    data = request.get_json()
    url = data.get("url", "")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    article = placeholder_fetch_article(url)
    dialog = placeholder_generate_script(article)

    session["dialog"] = dialog
    session["stage"] = 2

    return jsonify({"success": True, "dialog": dialog})


@app.route("/api/upload-reference", methods=["POST"])
def api_upload_reference():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    speaker = request.form.get("speaker", "A")
    transcript = request.form.get("transcript", "")

    filename = file.filename
    if not filename:
        return jsonify({"error": "No file selected"}), 400

    if not filename.endswith(".wav"):
        return jsonify({"error": "Only WAV files are supported"}), 400

    filename = f"speaker_{speaker}_{int(time.time())}.wav"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    placeholder_upload_reference_audio(filename, transcript)

    if speaker == "A":
        session["voice_a"] = filename
    else:
        session["voice_b"] = filename

    return jsonify({"success": True, "filename": filename})


@app.route("/uploads/ref_voices/<filename>")
def serve_uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/placaholders/<path:filename>")
def serve_placeholder_file(filename):
    return send_from_directory("placaholders", filename)


@app.route("/api/generate-clones", methods=["POST"])
def api_generate_clones():
    if not session.get("voice_a") or not session.get("voice_b"):
        return jsonify({"error": "Both speakers must have reference audio"}), 400

    def generate():
        for step in placeholder_generate_voice_clones():
            yield f"data: {json.dumps({'step': step})}\n\n"

    return app.response_class(generate(), mimetype="text/event-stream")


@app.route("/api/generate-podcast", methods=["POST"])
def api_generate_podcast():
    if not session.get("dialog"):
        return jsonify({"error": "No dialog script available"}), 400

    session["podcast_ready"] = True

    def generate():
        for step in placeholder_generate_podcast():
            yield f"data: {json.dumps({'step': step})}\n\n"

    return app.response_class(generate(), mimetype="text/event-stream")


@app.route("/api/reset", methods=["POST"])
def api_reset():
    session.clear()
    for filename in os.listdir(app.config["UPLOAD_FOLDER"]):
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        if os.path.isfile(filepath):
            os.remove(filepath)
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
