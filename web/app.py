import os
import sys
import json
import io
import base64
import time
import asyncio
from uuid import uuid4

import httpx
import soundfile as sf
import numpy as np
from flask import Flask, render_template, request, session, jsonify, send_from_directory, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.scriptMaker import ScriptMaker
from utils.wavCombiner import combine_wavs_interleaved
from job_queue import JobQueue
from project_store import (
    load_projects,
    save_project,
    get_project,
    delete_project,
    load_voices,
    save_voice,
    delete_voice,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "podcast-generator-secret-key")
app.config["UPLOAD_FOLDER"] = "uploads/ref_voices"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

TTS_API_URL = os.environ.get("TTS_API_URL", "http://127.0.0.1:8091")
job_queue = JobQueue()

PLACEHOLDER_DIALOG = "placaholders/LOG_dialog.json"


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
    return render_template("index.html", stage=session.get("stage", 1))


@app.route("/projects")
def projects_page():
    projects = load_projects()
    return render_template("projects.html", projects_json=json.dumps(
        [
            {
                "id": p["id"],
                "article_url": p.get("article_url", ""),
                "article_title": p.get("article_title", "Untitled"),
                "created_at": p.get("created_at", ""),
                "podcast_file": p.get("podcast_file", ""),
            }
            for p in projects
        ]
    ))


@app.route("/project/<project_id>")
def project_page(project_id):
    project = get_project(project_id)
    if not project:
        return "Project not found", 404
    return render_template("project.html", project=project)


@app.route("/api/fetch-article", methods=["POST"])
def api_fetch_article():
    data = request.get_json()
    url = data.get("url", "")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    script_maker = ScriptMaker()

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        dialog = loop.run_until_complete(script_maker.generateScript(url=url, log_path="./logs"))
        loop.close()
    except Exception as e:
        return jsonify({"error": f"Failed to generate script: {str(e)}"}), 500

    if not dialog or not dialog.get("script"):
        return jsonify({"error": "Could not generate a script from this article"}), 500

    session["dialog"] = dialog
    session["stage"] = 2
    session["article_url"] = url

    return jsonify({"success": True, "dialog": dialog})


@app.route("/api/upload-reference", methods=["POST"])
def api_upload_reference():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    speaker = request.form.get("speaker", "A")
    transcript = request.form.get("transcript", "")

    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.endswith(".wav"):
        return jsonify({"error": "Only WAV files are supported"}), 400

    local_filename = f"speaker_{speaker}_{int(time.time())}.wav"
    local_filepath = os.path.join(app.config["UPLOAD_FOLDER"], local_filename)
    file.save(local_filepath)

    voice_name = f"{app.secret_key}_{speaker}_{int(time.time())}"

    try:
        with open(local_filepath, "rb") as f:
            resp = httpx.post(
                f"{TTS_API_URL}/voices",
                files={"audio_sample": (local_filename, f, "audio/wav")},
                data={"name": voice_name, "ref_text": transcript},
                timeout=120,
            )
        if resp.status_code != 200:
            return jsonify({"error": f"TTS server error: {resp.text}"}), 500
    except httpx.ConnectError:
        return jsonify(
            {"error": "TTS server is not running. Start it with: python local_tts_server.py"}
        ), 503

    if speaker == "A":
        session["voice_a"] = voice_name
    else:
        session["voice_b"] = voice_name

    return jsonify({"success": True, "filename": local_filename, "voice_name": voice_name})


@app.route("/uploads/ref_voices/<filename>")
def serve_uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/placaholders/<path:filename>")
def serve_placeholder_file(filename):
    return send_from_directory("placaholders", filename)


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "podcasts")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _generate_podcast_job(
    dialog: dict,
    voice_a_name: str,
    voice_b_name: str,
    _report=None,
) -> str:
    topic = dialog.get("topic", dialog.get("title", ""))
    lines_a = [topic] + [entry["text"] for entry in dialog["script"] if entry["speaker"] == "Host_A"]
    lines_b = [entry["text"] for entry in dialog["script"] if entry["speaker"] == "Host_B"]

    if _report:
        _report(10)

    resp_a = httpx.post(
        f"{TTS_API_URL}/speech/batch",
        json={
            "items": [{"input": t} for t in lines_a],
            "voice": voice_a_name,
        },
        timeout=600,
    )
    if resp_a.status_code != 200:
        raise RuntimeError(f"TTS batch failed for speaker A: {resp_a.text}")

    if _report:
        _report(40)

    resp_b = httpx.post(
        f"{TTS_API_URL}/speech/batch",
        json={
            "items": [{"input": t} for t in lines_b],
            "voice": voice_b_name,
        },
        timeout=600,
    )
    if resp_b.status_code != 200:
        raise RuntimeError(f"TTS batch failed for speaker B: {resp_b.text}")

    if _report:
        _report(70)

    wavs_a = []
    for r in resp_a.json()["results"]:
        if r["status"] == "success":
            buf = io.BytesIO(base64.b64decode(r["audio_data"]))
            wav, _sr = sf.read(buf)
            wavs_a.append(wav)

    wavs_b = []
    for r in resp_b.json()["results"]:
        if r["status"] == "success":
            buf = io.BytesIO(base64.b64decode(r["audio_data"]))
            wav, _sr = sf.read(buf)
            wavs_b.append(wav)

    if _report:
        _report(85)

    combined = combine_wavs_interleaved(wavs_a[0], wavs_a[1:], wavs_b, _sr, 0.5)

    output_filename = f"podcast_{uuid4().hex[:8]}.wav"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    sf.write(output_path, combined, _sr)

    if _report:
        _report(100)

    return output_filename


@app.route("/api/generate-clones", methods=["POST"])
def api_generate_clones():
    if not session.get("voice_a") or not session.get("voice_b"):
        return jsonify({"error": "Both speakers must have reference audio"}), 400

    def generate():
        steps = [
            "Analyzing reference audio A...",
            "Speaker A voice clone ready.",
            "Analyzing reference audio B...",
            "Speaker B voice clone ready.",
            "Voice clones generated successfully!",
        ]
        for step in steps:
            yield f"data: {json.dumps({'step': step})}\n\n"

    return app.response_class(generate(), mimetype="text/event-stream")


@app.route("/api/generate-podcast", methods=["POST"])
def api_generate_podcast():
    dialog = session.get("dialog")
    if not dialog:
        return jsonify({"error": "No dialog script available"}), 400

    voice_a = session.get("voice_a")
    voice_b = session.get("voice_b")
    if not voice_a or not voice_b:
        return jsonify({"error": "Both speakers must have reference audio"}), 400

    jid = job_queue.submit(
        _generate_podcast_job,
        dialog=dialog,
        voice_a_name=voice_a,
        voice_b_name=voice_b,
    )

    _saved = False
    _article_url = session.get("article_url", "")

    def generate():
        nonlocal _saved
        last_progress = -1
        while True:
            job = job_queue.get(jid)
            if job is None:
                yield f"data: {json.dumps({'step': 'Unknown job ID', 'status': 'error'})}\n\n"
                return

            if job["status"] == "failed":
                yield f"data: {json.dumps({'step': job['error'], 'status': 'failed'})}\n\n"
                return

            pct = job.get("progress", 0)
            if pct != last_progress:
                last_progress = pct
                if pct == 0 and job["status"] == "queued":
                    yield f"data: {json.dumps({'step': 'Queued for generation...', 'progress': pct})}\n\n"
                elif job["status"] == "processing":
                    yield f"data: {json.dumps({'step': f'Generating podcast... {pct}%', 'progress': pct})}\n\n"

            if job["status"] == "done":
                podcast_file = job["result"]
                if not _saved:
                    _saved = True
                    save_project({
                        "id": jid,
                        "article_url": _article_url,
                        "article_title": dialog.get("title", ""),
                        "podcast_file": podcast_file,
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "dialog": dialog,
                        "voice_a_name": voice_a,
                        "voice_b_name": voice_b,
                    })
                yield f"data: {json.dumps({'step': 'Podcast generated successfully!', 'progress': 100, 'status': 'done', 'audio_url': f'/static/podcasts/{podcast_file}'})}\n\n"
                return

            time.sleep(0.5)

    return app.response_class(generate(), mimetype="text/event-stream")


@app.route("/api/projects", methods=["GET"])
def api_projects():
    projects = load_projects()
    return jsonify([
        {
            "id": p["id"],
            "article_url": p.get("article_url", ""),
            "article_title": p.get("article_title", "Untitled"),
            "created_at": p.get("created_at", ""),
            "podcast_file": p.get("podcast_file", ""),
        }
        for p in projects
    ])


@app.route("/api/projects/<project_id>", methods=["GET"])
def api_project(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(project)


@app.route("/api/projects/<project_id>", methods=["DELETE"])
def api_delete_project(project_id):
    delete_project(project_id)
    return jsonify({"success": True})


@app.route("/api/voices/list", methods=["GET"])
def api_voices_list():
    return jsonify(load_voices())


@app.route("/api/voices/save", methods=["POST"])
def api_voices_save():
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Voice name is required"}), 400

    voice_a = session.get("voice_a")
    voice_b = session.get("voice_b")

    ref_voice = None
    if data.get("speaker") == "A":
        ref_voice = voice_a
    elif data.get("speaker") == "B":
        ref_voice = voice_b
    else:
        return jsonify({"error": "Invalid speaker"}), 400

    if not ref_voice:
        return jsonify({"error": "No voice cloned for this speaker yet"}), 400

    save_voice({
        "name": name,
        "tts_name": ref_voice,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    return jsonify({"success": True, "name": name})


@app.route("/api/voices/delete", methods=["POST"])
def api_voices_delete():
    data = request.get_json()
    name = data.get("name", "")
    delete_voice(name)
    return jsonify({"success": True})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    session.clear()
    for filename in os.listdir(app.config["UPLOAD_FOLDER"]):
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        if os.path.isfile(filepath):
            os.remove(filepath)
    return jsonify({"success": True})


@app.route("/static/podcasts/<filename>")
def serve_podcast(filename):
    return send_from_directory(OUTPUT_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
