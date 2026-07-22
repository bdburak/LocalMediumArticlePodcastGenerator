import os
import sys
import json
import io
import base64
import time
import asyncio
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor, wait

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
)
from scripts_store import load_scripts, save_script, get_script, delete_script

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
    return render_template("dashboard.html")


@app.route("/scripts")
def scripts_page():
    return render_template("scripts.html")


@app.route("/scripts/<script_id>")
def script_page(script_id):
    script = get_script(script_id)
    if not script:
        return "Script not found", 404
    return render_template("script.html", project=script)


@app.route("/voices")
def voices_page():
    return render_template("voices.html")


@app.route("/studio")
def studio_page():
    return render_template("studio.html")


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

    if not dialog or dialog.get("error"):
        err = (dialog or {}).get("error", {})
        return jsonify({"error": err.get("message", "Scraping failed")}), 400

    if not dialog.get("script"):
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
            timeout=600,
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


@app.route("/api/voice-design", methods=["POST"])
def api_voice_design():
    data = request.get_json()
    speaker = data.get("speaker", "A")
    description = data.get("description", "").strip()
    language = data.get("language", "English")

    if not description:
        return jsonify({"error": "Voice description is required"}), 400

    voice_name = f"{app.secret_key}_{speaker}_vd_{int(time.time())}"

    try:
        resp = httpx.post(
            f"{TTS_API_URL}/voice-design",
            json={
                "name": voice_name,
                "description": description,
                "language": language,
            },
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

    return jsonify({"success": True, "voice_name": voice_name})


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

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_a = pool.submit(
            httpx.post,
            f"{TTS_API_URL}/speech/batch",
            json={
                "items": [{"input": t} for t in lines_a],
                "voice": voice_a_name,
            },
            timeout=600,
        )
        fut_b = pool.submit(
            httpx.post,
            f"{TTS_API_URL}/speech/batch",
            json={
                "items": [{"input": t} for t in lines_b],
                "voice": voice_b_name,
            },
            timeout=600,
        )
        wait([fut_a, fut_b])
        resp_a = fut_a.result()
        resp_b = fut_b.result()

    if resp_a.status_code != 200:
        raise RuntimeError(f"TTS batch failed for speaker A: {resp_a.text}")
    if resp_b.status_code != 200:
        raise RuntimeError(f"TTS batch failed for speaker B: {resp_b.text}")

    if _report:
        _report(40)

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


@app.route("/api/voices/library", methods=["GET"])
def api_voices_library():
    try:
        resp = httpx.get(f"{TTS_API_URL}/voices/list", timeout=10)
        if resp.status_code != 200:
            return jsonify([])
        return jsonify(resp.json())
    except httpx.ConnectError:
        return jsonify([])


@app.route("/api/voices/save", methods=["POST"])
def api_voices_save():
    data = request.get_json()
    display_name = data.get("display_name", "").strip()
    voice_type = data.get("voice_type", "clone")
    description = data.get("description", "")

    if not display_name:
        return jsonify({"error": "Voice name is required"}), 400

    speaker = data.get("speaker", "A")
    if speaker == "A":
        cache_name = session.get("voice_a")
    else:
        cache_name = session.get("voice_b")

    if not cache_name:
        return jsonify({"error": "No voice cloned for this speaker yet"}), 400

    try:
        resp = httpx.post(
            f"{TTS_API_URL}/voices/save",
            json={
                "name": cache_name,
                "display_name": display_name,
                "description": description,
                "voice_type": voice_type,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return jsonify({"error": f"TTS server error: {resp.text}"}), 500
    except httpx.ConnectError:
        return jsonify({"error": "TTS server is not running."}), 503

    if speaker == "A":
        session["voice_a"] = display_name
        session["voice_a_display"] = display_name
    else:
        session["voice_b"] = display_name
        session["voice_b_display"] = display_name

    return jsonify({"success": True, "display_name": display_name})


@app.route("/api/voices/select", methods=["POST"])
def api_voices_select():
    data = request.get_json()
    display_name = data.get("display_name", "").strip()
    speaker = data.get("speaker", "A")

    if not display_name:
        return jsonify({"error": "Voice name is required"}), 400

    try:
        resp = httpx.post(
            f"{TTS_API_URL}/voices/load",
            json={"display_name": display_name},
            timeout=30,
        )
        if resp.status_code != 200:
            return jsonify({"error": f"TTS server error: {resp.text}"}), 500

        result = resp.json()
        cache_name = result["name"]
    except httpx.ConnectError:
        return jsonify({"error": "TTS server is not running."}), 503

    if speaker == "A":
        session["voice_a"] = cache_name
        session["voice_a_display"] = display_name
    else:
        session["voice_b"] = cache_name
        session["voice_b_display"] = display_name

    return jsonify({"success": True, "display_name": display_name})


@app.route("/api/voices/delete", methods=["POST"])
def api_voices_delete():
    data = request.get_json()
    display_name = data.get("display_name", "")

    try:
        resp = httpx.post(
            f"{TTS_API_URL}/voices/delete",
            json={"display_name": display_name},
            timeout=10,
        )
        if resp.status_code != 200:
            return jsonify({"error": f"TTS server error: {resp.text}"}), 500
    except httpx.ConnectError:
        return jsonify({"error": "TTS server is not running."}), 503

    return jsonify({"success": True})


@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    scripts = load_scripts()
    try:
        voices_resp = httpx.get(f"{TTS_API_URL}/voices/list", timeout=10)
        voices = voices_resp.json() if voices_resp.status_code == 200 else []
    except httpx.ConnectError:
        voices = []
    projects = load_projects()

    return jsonify({
        "scripts_count": len(scripts),
        "voices_count": len(voices),
        "projects_count": len(projects),
        "recent_scripts": scripts[:5],
        "recent_voices": voices[:5],
        "recent_projects": projects[:5],
    })


@app.route("/api/scripts", methods=["GET"])
def api_scripts_list():
    return jsonify(load_scripts())


@app.route("/api/scripts/<script_id>", methods=["GET"])
def api_script_detail(script_id):
    script = get_script(script_id)
    if not script:
        return jsonify({"error": "Script not found"}), 404
    return jsonify(script)


@app.route("/api/scripts/create", methods=["POST"])
def api_script_create():
    data = request.get_json()
    url = data.get("url", "").strip()

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

    if not dialog or dialog.get("error"):
        err = (dialog or {}).get("error", {})
        return jsonify({"error": err.get("message", "Scraping failed")}), 400

    if not dialog.get("script"):
        return jsonify({"error": "Could not generate a script from this article"}), 500

    script_id = save_script({
        "article_url": url,
        "article_title": dialog.get("title", ""),
        "dialog": dialog,
        "turns": len(dialog.get("script", [])),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })

    return jsonify({
        "success": True,
        "id": script_id,
        "article_title": dialog.get("title", ""),
        "article_url": url,
    })


@app.route("/api/scripts/<script_id>", methods=["DELETE"])
def api_script_delete(script_id):
    delete_script(script_id)
    return jsonify({"success": True})


@app.route("/api/voices/preview", methods=["POST"])
def api_voices_preview():
    data = request.get_json()
    display_name = data.get("display_name", "").strip()
    text = data.get("text", "Hello, this is a voice preview.")

    if not display_name:
        return jsonify({"error": "Voice name is required"}), 400

    try:
        load_resp = httpx.post(
            f"{TTS_API_URL}/voices/load",
            json={"display_name": display_name},
            timeout=30,
        )
        if load_resp.status_code != 200:
            return jsonify({"error": "Failed to load voice"}), 500
        cache_name = load_resp.json()["name"]
    except httpx.ConnectError:
        return jsonify({"error": "TTS server is not running."}), 503

    try:
        resp = httpx.post(
            f"{TTS_API_URL}/speech",
            json={"input": text, "voice": cache_name},
            timeout=60,
        )
        if resp.status_code != 200:
            return jsonify({"error": f"TTS error: {resp.text}"}), 500
        return Response(resp.content, mimetype="audio/wav")
    except httpx.ConnectError:
        return jsonify({"error": "TTS server is not running."}), 503


@app.route("/api/studio/generate", methods=["POST"])
def api_studio_generate():
    data = request.get_json()
    script_id = data.get("script_id", "").strip()
    voice_a_name = data.get("voice_a_name", "").strip()
    voice_b_name = data.get("voice_b_name", "").strip()

    if not script_id or not voice_a_name or not voice_b_name:
        return jsonify({"error": "script_id, voice_a_name, and voice_b_name are required"}), 400

    script = get_script(script_id)
    if not script:
        return jsonify({"error": "Script not found"}), 404

    dialog = script["dialog"]

    def gen():
        try:
            load_a = httpx.post(
                f"{TTS_API_URL}/voices/load",
                json={"display_name": voice_a_name},
                timeout=30,
            )
            if load_a.status_code != 200:
                yield f"data: {json.dumps({'step': 'Failed to load voice A', 'status': 'failed'})}\n\n"
                return
            cache_a = load_a.json()["name"]

            load_b = httpx.post(
                f"{TTS_API_URL}/voices/load",
                json={"display_name": voice_b_name},
                timeout=30,
            )
            if load_b.status_code != 200:
                yield f"data: {json.dumps({'step': 'Failed to load voice B', 'status': 'failed'})}\n\n"
                return
            cache_b = load_b.json()["name"]

            yield f"data: {json.dumps({'step': 'Voices loaded. Generating podcast...', 'progress': 5})}\n\n"

            topic = dialog.get("topic", dialog.get("title", ""))
            lines_a = [topic] + [entry["text"] for entry in dialog["script"] if entry["speaker"] == "Host_A"]
            lines_b = [entry["text"] for entry in dialog["script"] if entry["speaker"] == "Host_B"]

            with ThreadPoolExecutor(max_workers=2) as pool:
                fut_a = pool.submit(
                    httpx.post,
                    f"{TTS_API_URL}/speech/batch",
                    json={"items": [{"input": t} for t in lines_a], "voice": cache_a},
                    timeout=600,
                )
                fut_b = pool.submit(
                    httpx.post,
                    f"{TTS_API_URL}/speech/batch",
                    json={"items": [{"input": t} for t in lines_b], "voice": cache_b},
                    timeout=600,
                )
                wait([fut_a, fut_b])
                resp_a = fut_a.result()
                resp_b = fut_b.result()

            if resp_a.status_code != 200:
                yield f"data: {json.dumps({'step': 'TTS failed for speaker A', 'status': 'failed'})}\n\n"
                return
            if resp_b.status_code != 200:
                yield f"data: {json.dumps({'step': 'TTS failed for speaker B', 'status': 'failed'})}\n\n"
                return
            yield f"data: {json.dumps({'step': 'Both speakers generated. Combining audio...', 'progress': 40})}\n\n"

            wavs_a = []
            for r in resp_a.json()["results"]:
                if r["status"] == "success":
                    buf = io.BytesIO(base64.b64decode(r["audio_data"]))
                    wav, sr = sf.read(buf)
                    wavs_a.append(wav)

            wavs_b = []
            for r in resp_b.json()["results"]:
                if r["status"] == "success":
                    buf = io.BytesIO(base64.b64decode(r["audio_data"]))
                    wav, sr = sf.read(buf)
                    wavs_b.append(wav)

            combined = combine_wavs_interleaved(wavs_a[0], wavs_a[1:], wavs_b, sr, 0.5)

            jid = uuid4().hex[:8]
            output_filename = f"podcast_{jid}.wav"
            output_path = os.path.join(OUTPUT_DIR, output_filename)
            sf.write(output_path, combined, sr)

            save_project({
                "id": jid,
                "article_url": script.get("article_url", ""),
                "article_title": script.get("article_title", ""),
                "podcast_file": output_filename,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "dialog": dialog,
                "voice_a_name": voice_a_name,
                "voice_b_name": voice_b_name,
            })

            yield f"data: {json.dumps({'step': 'Podcast generated!', 'progress': 100, 'status': 'done', 'project_id': jid, 'audio_url': f'/static/podcasts/{output_filename}'})}\n\n"

        except httpx.ConnectError:
            yield f"data: {json.dumps({'step': 'TTS server connection failed', 'status': 'failed'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'step': str(e), 'status': 'failed'})}\n\n"

    return app.response_class(gen(), mimetype="text/event-stream")


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
