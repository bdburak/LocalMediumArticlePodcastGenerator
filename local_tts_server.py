import io
import json
import base64
import tempfile
import os
import shutil
import time
from typing import List, Optional
from pydantic import BaseModel

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
import uvicorn
import soundfile as sf
import torch

from ttsClass import TTS
from qwen_tts import Qwen3TTSModel

app = FastAPI(title="Qwen3-TTS Local Server")

print("Loading TTS model...")
tts = TTS(temp_file_location=os.path.join(tempfile.gettempdir(), "qwen3_tts_server"))

voice_cache: dict[str, List] = {}
voice_design_model = None

VOICES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voices")
os.makedirs(VOICES_DIR, exist_ok=True)


def _load_voice_index():
    index_path = os.path.join(VOICES_DIR, "index.json")
    if os.path.exists(index_path):
        with open(index_path, "r") as f:
            return json.load(f).get("voices", [])
    return []


def _save_voice_index(voices):
    with open(os.path.join(VOICES_DIR, "index.json"), "w") as f:
        json.dump({"voices": voices}, f, indent=2)


def _save_voice_to_disk(name, clone_items, voice_type, description=""):
    filepath = os.path.join(VOICES_DIR, f"{name}.pt")
    torch.save(clone_items, filepath)
    created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    voices = _load_voice_index()
    voices = [v for v in voices if v["name"] != name]
    voices.append({
        "name": name,
        "type": voice_type,
        "description": description,
        "created_at": created_at,
        "file": f"{name}.pt",
    })
    _save_voice_index(voices)


def _load_voice_from_disk(name):
    filepath = os.path.join(VOICES_DIR, f"{name}.pt")
    if not os.path.exists(filepath):
        return None
    return torch.load(filepath, weights_only=False)


def get_voice_design_model():
    global voice_design_model
    if voice_design_model is None:
        print("Loading VoiceDesign model...")
        voice_design_model = Qwen3TTSModel.from_pretrained(
            "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
            device_map="cuda:0",
            dtype=torch.bfloat16,
            attn_implementation="sdpa",
        )
    return voice_design_model


class SpeechRequest(BaseModel):
    input: str
    voice: str
    language: str = "English"


class BatchItem(BaseModel):
    input: str


class BatchRequest(BaseModel):
    items: List[BatchItem]
    voice: str
    language: str = "English"


class VoiceDesignRequest(BaseModel):
    name: str
    description: str
    language: str = "English"


class SaveVoiceRequest(BaseModel):
    name: str
    display_name: str
    description: str = ""
    voice_type: str = "clone"


class LoadVoiceRequest(BaseModel):
    display_name: str


class DeleteVoiceRequest(BaseModel):
    display_name: str


@app.post("/voices")
async def upload_voice(
    audio_sample: UploadFile = File(...),
    name: str = Form(...),
    ref_text: str = Form(""),
):
    if not audio_sample.filename:
        raise HTTPException(400, "No file provided")

    tmp_path = os.path.join(tempfile.gettempdir(), f"voice_{name}_{os.urandom(4).hex()}.wav")
    try:
        contents = await audio_sample.read()
        with open(tmp_path, "wb") as f:
            f.write(contents)

        clone_items = tts.create_voice_clone_prompt_items(
            reference_audio_path=tmp_path,
            reference_text=ref_text,
        )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    voice_cache[name] = clone_items
    return {"name": name, "success": True}


@app.post("/voice-design")
def create_voice_design(request: VoiceDesignRequest):
    model = get_voice_design_model()

    test_phrase = "Hello, this is a voice design test."
    wavs, sr = model.generate_voice_design(
        text=test_phrase,
        instruct=request.description,
        language=request.language,
    )

    clone_items = tts.model.create_voice_clone_prompt(
        ref_audio=(wavs[0], sr),
        ref_text=test_phrase,
    )

    voice_cache[request.name] = clone_items
    return {"name": request.name, "success": True}


@app.post("/voices/save")
def save_voice(request: SaveVoiceRequest):
    clone_items = voice_cache.get(request.name)
    if clone_items is None:
        raise HTTPException(404, f"Voice '{request.name}' not found in cache.")

    _save_voice_to_disk(request.display_name, clone_items, request.voice_type, request.description)
    voice_cache[request.display_name] = clone_items
    return {"display_name": request.display_name, "success": True}


@app.get("/voices/list")
def list_voices():
    return _load_voice_index()


@app.post("/voices/load")
def load_voice(request: LoadVoiceRequest):
    clone_items = _load_voice_from_disk(request.display_name)
    if clone_items is None:
        raise HTTPException(404, f"Saved voice '{request.display_name}' not found.")

    cache_name = f"_loaded_{request.display_name}"
    voice_cache[cache_name] = clone_items
    return {"name": cache_name, "display_name": request.display_name, "success": True}


@app.post("/voices/delete")
def delete_voice(request: DeleteVoiceRequest):
    filepath = os.path.join(VOICES_DIR, f"{request.display_name}.pt")
    if os.path.exists(filepath):
        os.remove(filepath)

    voices = _load_voice_index()
    voices = [v for v in voices if v["name"] != request.display_name]
    _save_voice_index(voices)

    voice_cache.pop(request.display_name, None)
    voice_cache.pop(f"_loaded_{request.display_name}", None)
    return {"success": True}


@app.post("/speech")
def generate_speech(request: SpeechRequest):
    clone_items = voice_cache.get(request.voice)
    if clone_items is None:
        raise HTTPException(404, f"Voice '{request.voice}' not found. Upload it first via POST /voices.")

    wav, sr = tts.generate_wav(
        text=request.input,
        voice_clone_prompt_items=clone_items,
        language=request.language,
    )

    buf = io.BytesIO()
    sf.write(buf, wav, sr, format="WAV")
    buf.seek(0)
    return Response(buf.read(), media_type="audio/wav")


@app.post("/speech/batch")
def generate_speech_batch(request: BatchRequest):
    t_start = time.perf_counter()
    clone_items = voice_cache.get(request.voice)
    if clone_items is None:
        raise HTTPException(404, f"Voice '{request.voice}' not found. Upload it first via POST /voices.")

    texts = [item.input for item in request.items]
    total_chars = sum(len(t) for t in texts)
    print(f"[PERF] /speech/batch voice={request.voice} lines={len(texts)} chars={total_chars}")

    flat_paths: List[str] = []
    batched = tts.generate_wav_batched(
        text=texts,
        voice_clone_prompt_items=clone_items,
        speaker_name=request.voice,
        language=request.language,
    )
    for batch_paths in batched:
        flat_paths.extend(batch_paths)

    t_encode = time.perf_counter()
    results = []
    total_audio_bytes = 0
    for i, path in enumerate(flat_paths):
        try:
            audio, sr = sf.read(path)
            buf = io.BytesIO()
            sf.write(buf, audio, sr, format="WAV")
            raw_bytes = buf.getvalue()
            b64 = base64.b64encode(raw_bytes).decode()
            total_audio_bytes += len(raw_bytes)
            results.append({
                "index": i,
                "status": "success",
                "audio_data": b64,
                "media_type": "audio/wav",
            })
        except Exception as e:
            results.append({
                "index": i,
                "status": "error",
                "error": str(e),
            })

    encode_time = time.perf_counter() - t_encode

    shutil.rmtree(f"{tts.temp_file_location}/{request.voice}", ignore_errors=True)

    elapsed = time.perf_counter() - t_start
    audio_mb = total_audio_bytes / 1024**2
    print(
        f"[PERF] /speech/batch voice={request.voice} DONE "
        f"total={elapsed:.1f}s encode={encode_time:.2f}s "
        f"clips={len(flat_paths)} audio={audio_mb:.1f}MB "
        f"b64+json={audio_mb*1.33:.1f}MB"
    )

    return {
        "results": results,
        "total": len(results),
        "succeeded": sum(1 for r in results if r["status"] == "success"),
        "failed": sum(1 for r in results if r["status"] == "error"),
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "voices": list(voice_cache.keys()),
        "model_loaded": tts.model is not None,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8091)
