from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Voice Design API Wrapper", version="1.0.0")

WORK_DIR = Path(os.path.expandvars(os.getenv("VOICE_DESIGN_WORK_DIR", "$HOME/Qwen-Qwen3-TTS-12Hz-1.7B-VoiceDesign"))).expanduser()
OUTPUT_DIR = Path(os.getenv("VOICE_DESIGN_OUTPUT_DIR", "/tmp/qwen3_tts_output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class InferRequest(BaseModel):
    text: str
    instruct: str = ""
    language: str = "Chinese"


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "work_dir": str(WORK_DIR),
        "output_dir": str(OUTPUT_DIR),
    }


@app.post("/infer")
async def infer(req: InferRequest) -> FileResponse:
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")

    out_file = OUTPUT_DIR / f"{uuid.uuid4().hex}.wav"
    cmd = (
        "python -c \"import os; import torch; import soundfile as sf; "
        "from qwen_tts import Qwen3TTSModel; "
        "text = os.environ.get('TEXT', ''); "
        "instruct = os.environ.get('INSTRUCT', ''); "
        "language = os.environ.get('LANG', 'Auto'); "
        "model = Qwen3TTSModel.from_pretrained("
        "'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign', "
        "device_map='cuda:0', dtype=torch.bfloat16, attn_implementation='flash_attention_2'); "
        "wavs, sr = model.generate_voice_design(text=text, instruct=instruct, language=language); "
        "sf.write(os.environ.get('OUT_FILE'), wavs[0], sr); print('Success')\""
    )
    shell_cmd = os.getenv("VOICE_DESIGN_COMMAND", cmd)

    env = os.environ.copy()
    env["TEXT"] = text
    env["INSTRUCT"] = req.instruct
    env["LANG"] = req.language
    env["OUT_FILE"] = str(out_file)

    try:
        proc = subprocess.run(
            shell_cmd,
            shell=True,
            cwd=str(WORK_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("VOICE_DESIGN_TIMEOUT", "1800")),
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail=f"voice_design timeout: {exc}") from exc

    if proc.returncode != 0:
        detail = f"voice_design failed: {proc.stderr[-2000:] or proc.stdout[-2000:]}"
        raise HTTPException(status_code=503, detail=detail)
    if not out_file.exists():
        raise HTTPException(status_code=503, detail="voice_design 未生成输出文件")

    return FileResponse(str(out_file), media_type="audio/wav", filename=out_file.name)
