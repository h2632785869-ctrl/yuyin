from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

app = FastAPI(title="MMAudio API Wrapper", version="1.0.0")

WORK_DIR = Path(os.path.expandvars(os.getenv("ENV_AUDIO_WORK_DIR", "$HOME/MMAudio"))).expanduser()
OUTPUT_DIR = Path(os.getenv("ENV_AUDIO_OUTPUT_DIR", "/tmp/results/MMAudio-api"))
UPLOAD_DIR = Path(os.getenv("ENV_AUDIO_UPLOAD_DIR", "/tmp/uploads/MMAudio-api"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "work_dir": str(WORK_DIR),
        "output_dir": str(OUTPUT_DIR),
    }


@app.post("/infer")
async def infer(
    video: UploadFile = File(...),
    prompt: str = Form(""),
    negative_prompt: str = Form(""),
    audio_mix_mode: str = Form("mix"),
    ambient_volume: str = Form("0.25"),
    bgm_volume: str = Form("0.3"),
    num_steps: str = Form("25"),
    cfg_strength: str = Form("4.5"),
) -> FileResponse:
    task_id = uuid.uuid4().hex
    task_upload_dir = UPLOAD_DIR / task_id
    task_upload_dir.mkdir(parents=True, exist_ok=True)
    input_video = task_upload_dir / Path(video.filename or "input.mp4").name
    with input_video.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    task_output_dir = OUTPUT_DIR / task_id
    task_output_dir.mkdir(parents=True, exist_ok=True)
    output_video = task_output_dir / "output.mp4"

    cmd = (
        "python demo.py "
        "--variant large_44k_v2 "
        "--video \"$VIDEO\" "
        "--prompt \"$PROMPT\" "
        "--negative_prompt \"$NEGATIVE_PROMPT\" "
        "--cfg_strength \"$CFG_STRENGTH\" "
        "--num_steps \"$NUM_STEPS\" "
        "--seed 42 "
        "--output \"$OUT_DIR\" "
        "--skip_video_composite"
    )
    shell_cmd = os.getenv("ENV_AUDIO_COMMAND", cmd)

    env = os.environ.copy()
    env["VIDEO"] = str(input_video)
    env["PROMPT"] = prompt
    env["NEGATIVE_PROMPT"] = negative_prompt
    env["AUDIO_MIX_MODE"] = audio_mix_mode
    env["AMBIENT_VOLUME"] = ambient_volume
    env["BGM_VOLUME"] = bgm_volume
    env["NUM_STEPS"] = num_steps
    env["CFG_STRENGTH"] = cfg_strength
    env["OUT_DIR"] = str(task_output_dir)

    try:
        proc = subprocess.run(
            shell_cmd,
            shell=True,
            cwd=str(WORK_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("ENV_AUDIO_TIMEOUT", "7200")),
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"env_audio timeout: {exc}") from exc

    if proc.returncode != 0:
        detail = f"env_audio failed: {proc.stderr[-3000:] or proc.stdout[-3000:]}"
        raise HTTPException(status_code=503, detail=detail)

    # 优先使用标准输出文件名，否则在输出目录中兜底查找第一个 mp4。
    if not output_video.exists():
        candidates = sorted(task_output_dir.glob("*.mp4"))
        if not candidates:
            raise HTTPException(status_code=503, detail="env_audio 未生成输出视频")
        output_video = candidates[0]

    return FileResponse(str(output_video), media_type="video/mp4", filename=output_video.name)
