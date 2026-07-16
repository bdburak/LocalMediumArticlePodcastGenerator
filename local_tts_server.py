import io
import base64
import tempfile
import os
import shutil
from typing import List, Optional
from pydantic import BaseModel

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
import uvicorn
import soundfile as sf
import torch

from ttsClass import TTS

app = FastAPI(title="Qwen3-TTS Local Server")

print("Loading TTS model...")
tts = TTS(temp_file_location=os.path.join(tempfile.gettempdir(), "qwen3_tts_server"))

voice_cache: dict[str, List] = {}


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
    clone_items = voice_cache.get(request.voice)
    if clone_items is None:
        raise HTTPException(404, f"Voice '{request.voice}' not found. Upload it first via POST /voices.")

    texts = [item.input for item in request.items]

    flat_paths: List[str] = []
    batched = tts.generate_wav_batched(
        text=texts,
        voice_clone_prompt_items=clone_items,
        speaker_name=request.voice,
        language=request.language,
    )
    for batch_paths in batched:
        flat_paths.extend(batch_paths)

    results = []
    for i, path in enumerate(flat_paths):
        try:
            audio, sr = sf.read(path)
            buf = io.BytesIO()
            sf.write(buf, audio, sr, format="WAV")
            b64 = base64.b64encode(buf.getvalue()).decode()
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

    shutil.rmtree(f"{tts.temp_file_location}/{request.voice}", ignore_errors=True)

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
