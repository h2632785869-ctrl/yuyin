from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

app = FastAPI(title="IndexTTS API Wrapper", version="1.0.0")

WORK_DIR = Path(os.path.expandvars(os.getenv("TTS_WORK_DIR", "$HOME/index-tts-workspace"))).expanduser()
MODEL_DIR = Path(os.path.expandvars(os.getenv("TTS_MODEL_DIR", "$HOME/.cache/index-tts"))).expanduser()
OUTPUT_DIR = Path(os.getenv("TTS_OUTPUT_DIR", "/tmp/index-tts-output"))
UPLOAD_DIR = Path(os.getenv("TTS_UPLOAD_DIR", "/tmp/index-tts-uploads"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "work_dir": str(WORK_DIR),
        "model_dir": str(MODEL_DIR),
        "output_dir": str(OUTPUT_DIR),
    }


@app.post("/infer")
async def infer(
    text_input: str = Form(...),
    emotion_happy: float = Form(0),
    emotion_angry: float = Form(0),
    emotion_sad: float = Form(0),
    emotion_fear: float = Form(0),
    emotion_disgust: float = Form(0),
    emotion_melancholy: float = Form(0),
    emotion_surprise: float = Form(0),
    emotion_calm: float = Form(0),
    use_random: str = Form("False"),
    reference_audio: UploadFile = File(...),
) -> FileResponse:
    text = text_input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text_input 不能为空")

    task_id = uuid.uuid4().hex
    task_upload_dir = UPLOAD_DIR / task_id
    task_upload_dir.mkdir(parents=True, exist_ok=True)
    ref_file = task_upload_dir / Path(reference_audio.filename or "reference.wav").name
    with ref_file.open("wb") as f:
        shutil.copyfileobj(reference_audio.file, f)

    out_file = OUTPUT_DIR / f"{task_id}.wav"
    cmd = (
        "uv run python -c \"import os; from indextts.infer_v2 import IndexTTS2; "
        "emo_vector=[float(os.environ.get('EMO_HAPPY', 0)) * 0.01, "
        "float(os.environ.get('EMO_ANGRY', 0)) * 0.01, "
        "float(os.environ.get('EMO_SAD', 0)) * 0.01, "
        "float(os.environ.get('EMO_FEAR', 0)) * 0.01, "
        "float(os.environ.get('EMO_DISGUST', 0)) * 0.01, "
        "float(os.environ.get('EMO_MELANCHOLY', 0)) * 0.01, "
        "float(os.environ.get('EMO_SURPRISE', 0)) * 0.01, "
        "float(os.environ.get('EMO_CALM', 0)) * 0.01]; "
        "tts = IndexTTS2(cfg_path='checkpoints/config.yaml', model_dir=os.environ.get('MODEL_DIR'), "
        "use_fp16=True, use_cuda_kernel=True, use_deepspeed=False); "
        "tts.infer(spk_audio_prompt=os.environ.get('REF_AUDIO'), text=os.environ.get('TEXT_INPUT'), "
        "output_path=os.environ.get('OUT_FILE'), emo_vector=emo_vector, "
        "use_random=eval(os.environ.get('USE_RANDOM')), verbose=True)\""
    )
    shell_cmd = os.getenv("TTS_COMMAND", cmd)

    env = os.environ.copy()
    env["TEXT_INPUT"] = text
    env["REF_AUDIO"] = str(ref_file)
    env["EMO_HAPPY"] = str(emotion_happy)
    env["EMO_ANGRY"] = str(emotion_angry)
    env["EMO_SAD"] = str(emotion_sad)
    env["EMO_FEAR"] = str(emotion_fear)
    env["EMO_DISGUST"] = str(emotion_disgust)
    env["EMO_MELANCHOLY"] = str(emotion_melancholy)
    env["EMO_SURPRISE"] = str(emotion_surprise)
    env["EMO_CALM"] = str(emotion_calm)
    env["USE_RANDOM"] = use_random
    env["OUT_FILE"] = str(out_file)
    env["MODEL_DIR"] = str(MODEL_DIR)

    try:
        proc = subprocess.run(
            shell_cmd,
            shell=True,
            cwd=str(WORK_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("TTS_TIMEOUT", "1800")),
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"tts timeout: {exc}") from exc

    if proc.returncode != 0:
        detail = f"tts failed: {proc.stderr[-2000:] or proc.stdout[-2000:]}"
        raise HTTPException(status_code=503, detail=detail)
    if not out_file.exists():
        raise HTTPException(status_code=503, detail="tts 未生成输出文件")

    return FileResponse(str(out_file), media_type="audio/wav", filename=out_file.name)
