from __future__ import annotations

import asyncio
import json
import os
import subprocess
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import httpx
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

TaskStatus = Literal["queued", "running", "done", "failed"]

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

VOICE_DESIGN_URL = os.getenv("VOICE_DESIGN_URL", "http://127.0.0.1:9101/infer")
TTS_URL = os.getenv("TTS_URL", "http://127.0.0.1:9102/infer")
ENV_AUDIO_URL = os.getenv("ENV_AUDIO_URL", "http://127.0.0.1:9103/infer")

# 如果你的服务接收字段名不同，直接改环境变量即可。
VOICE_DESIGN_TEXT_FIELD = os.getenv("VOICE_DESIGN_TEXT_FIELD", "text")
VOICE_DESIGN_INSTRUCT_FIELD = os.getenv("VOICE_DESIGN_INSTRUCT_FIELD", "instruct")
VOICE_DESIGN_LANGUAGE_FIELD = os.getenv("VOICE_DESIGN_LANGUAGE_FIELD", "language")

TTS_TEXT_FIELD = os.getenv("TTS_TEXT_FIELD", "text_input")
TTS_REF_AUDIO_FIELD = os.getenv("TTS_REF_AUDIO_FIELD", "reference_audio")
TTS_EMOTION_HAPPY_FIELD = os.getenv("TTS_EMOTION_HAPPY_FIELD", "emotion_happy")
TTS_EMOTION_ANGRY_FIELD = os.getenv("TTS_EMOTION_ANGRY_FIELD", "emotion_angry")
TTS_EMOTION_SAD_FIELD = os.getenv("TTS_EMOTION_SAD_FIELD", "emotion_sad")
TTS_EMOTION_FEAR_FIELD = os.getenv("TTS_EMOTION_FEAR_FIELD", "emotion_fear")
TTS_EMOTION_DISGUST_FIELD = os.getenv("TTS_EMOTION_DISGUST_FIELD", "emotion_disgust")
TTS_EMOTION_MELANCHOLY_FIELD = os.getenv("TTS_EMOTION_MELANCHOLY_FIELD", "emotion_melancholy")
TTS_EMOTION_SURPRISE_FIELD = os.getenv("TTS_EMOTION_SURPRISE_FIELD", "emotion_surprise")
TTS_EMOTION_CALM_FIELD = os.getenv("TTS_EMOTION_CALM_FIELD", "emotion_calm")
TTS_USE_RANDOM_FIELD = os.getenv("TTS_USE_RANDOM_FIELD", "use_random")

ENV_VIDEO_FIELD = os.getenv("ENV_VIDEO_FIELD", "video")
ENV_PROMPT_FIELD = os.getenv("ENV_PROMPT_FIELD", "prompt")
ENV_NEGATIVE_PROMPT_FIELD = os.getenv("ENV_NEGATIVE_PROMPT_FIELD", "negative_prompt")
ENV_AUDIO_MIX_MODE_FIELD = os.getenv("ENV_AUDIO_MIX_MODE_FIELD", "audio_mix_mode")
ENV_AMBIENT_VOLUME_FIELD = os.getenv("ENV_AMBIENT_VOLUME_FIELD", "ambient_volume")
ENV_BGM_VOLUME_FIELD = os.getenv("ENV_BGM_VOLUME_FIELD", "bgm_volume")
ENV_NUM_STEPS_FIELD = os.getenv("ENV_NUM_STEPS_FIELD", "num_steps")
ENV_CFG_STRENGTH_FIELD = os.getenv("ENV_CFG_STRENGTH_FIELD", "cfg_strength")


class TaskRecord(BaseModel):
    task_id: str
    module: str
    status: TaskStatus
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    result: Optional[Any] = None
    output_file: Optional[str] = None
    payload: Dict[str, Any]


app = FastAPI(title="H5 三模块网关", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

task_store: Dict[str, TaskRecord] = {}
task_queue: asyncio.Queue[str] = asyncio.Queue()
running_task_id: Optional[str] = None
worker_handle: Optional[asyncio.Task[None]] = None


def release_gpu_memory() -> None:
    """
    尝试在每个任务后回收显存。
    即使当前环境没有 torch，也不影响主流程。
    """
    try:
        subprocess.run(
            [
                "python3",
                "-c",
                "import torch; torch.cuda.empty_cache(); print('cuda cache cleared')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        # 清理失败不应影响队列执行
        pass


def save_upload(task_id: str, upload: UploadFile, subdir: str) -> str:
    safe_name = Path(upload.filename or f"{uuid.uuid4().hex}.bin").name
    task_dir = UPLOAD_DIR / subdir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    dst = task_dir / safe_name
    with dst.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return str(dst)


async def call_json_service(url: str, payload: Dict[str, Any]) -> tuple[Any, Optional[str]]:
    timeout = httpx.Timeout(900.0, connect=20.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            return resp.json(), None
        if content_type.startswith("audio/") or content_type.startswith("video/") or "octet-stream" in content_type:
            ext = ".bin"
            if content_type.startswith("audio/"):
                ext = ".wav"
            elif content_type.startswith("video/"):
                ext = ".mp4"
            out_file = OUTPUT_DIR / f"{uuid.uuid4().hex}{ext}"
            out_file.write_bytes(resp.content)
            return {"message": "binary saved", "size": len(resp.content)}, str(out_file)
        return {"text": resp.text}, None


async def call_multipart_service(
    url: str,
    data: Dict[str, Any],
    file_field: str,
    file_path: str,
) -> tuple[Any, Optional[str]]:
    timeout = httpx.Timeout(1800.0, connect=30.0)
    filename = Path(file_path).name
    async with httpx.AsyncClient(timeout=timeout) as client:
        with open(file_path, "rb") as f:
            files = {file_field: (filename, f)}
            resp = await client.post(url, data=data, files=files)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            data = resp.json()
            output_file = data.get("output_file") if isinstance(data, dict) else None
            return data, output_file
        if content_type.startswith("audio/") or content_type.startswith("video/") or "octet-stream" in content_type:
            ext = ".bin"
            if content_type.startswith("audio/"):
                ext = ".wav"
            elif content_type.startswith("video/"):
                ext = ".mp4"
            out_file = OUTPUT_DIR / f"{uuid.uuid4().hex}{ext}"
            out_file.write_bytes(resp.content)
            return {"message": "binary saved", "size": len(resp.content)}, str(out_file)
        return {"text": resp.text}, None


async def dispatch_task(task: TaskRecord) -> tuple[Any, Optional[str]]:
    p = task.payload
    module = task.module

    if module == "voice_design":
        payload = {
            VOICE_DESIGN_TEXT_FIELD: p["text"],
            VOICE_DESIGN_INSTRUCT_FIELD: p.get("instruct", ""),
            VOICE_DESIGN_LANGUAGE_FIELD: p["language"],
        }
        return await call_json_service(VOICE_DESIGN_URL, payload)

    if module == "tts":
        data = {
            TTS_TEXT_FIELD: p["text_input"],
            TTS_EMOTION_HAPPY_FIELD: p["emotion_happy"],
            TTS_EMOTION_ANGRY_FIELD: p["emotion_angry"],
            TTS_EMOTION_SAD_FIELD: p["emotion_sad"],
            TTS_EMOTION_FEAR_FIELD: p["emotion_fear"],
            TTS_EMOTION_DISGUST_FIELD: p["emotion_disgust"],
            TTS_EMOTION_MELANCHOLY_FIELD: p["emotion_melancholy"],
            TTS_EMOTION_SURPRISE_FIELD: p["emotion_surprise"],
            TTS_EMOTION_CALM_FIELD: p["emotion_calm"],
            TTS_USE_RANDOM_FIELD: p["use_random"],
        }
        return await call_multipart_service(TTS_URL, data, TTS_REF_AUDIO_FIELD, p["reference_audio_path"])

    if module == "env_audio":
        data = {
            ENV_PROMPT_FIELD: p.get("prompt", ""),
            ENV_NEGATIVE_PROMPT_FIELD: p.get("negative_prompt", ""),
            ENV_AUDIO_MIX_MODE_FIELD: p["audio_mix_mode"],
            ENV_AMBIENT_VOLUME_FIELD: p["ambient_volume"],
            ENV_BGM_VOLUME_FIELD: p["bgm_volume"],
            ENV_NUM_STEPS_FIELD: p["num_steps"],
            ENV_CFG_STRENGTH_FIELD: p["cfg_strength"],
        }
        return await call_multipart_service(ENV_AUDIO_URL, data, ENV_VIDEO_FIELD, p["video_path"])

    raise HTTPException(status_code=400, detail=f"未知模块: {module}")


async def worker_loop() -> None:
    global running_task_id
    while True:
        task_id = await task_queue.get()
        record = task_store.get(task_id)
        if not record:
            task_queue.task_done()
            continue
        running_task_id = task_id
        record.status = "running"
        record.started_at = time.time()
        try:
            result, output_file = await dispatch_task(record)
            record.status = "done"
            record.result = result
            if output_file:
                record.output_file = output_file
        except Exception as exc:  # noqa: BLE001
            record.status = "failed"
            record.error = f"{type(exc).__name__}: {exc}"
        finally:
            record.finished_at = time.time()
            release_gpu_memory()
            running_task_id = None
            task_queue.task_done()


@app.on_event("startup")
async def startup() -> None:
    global worker_handle
    if worker_handle is None or worker_handle.done():
        worker_handle = asyncio.create_task(worker_loop())


def enqueue_task(module: str, payload: Dict[str, Any], task_id: Optional[str] = None) -> Dict[str, Any]:
    if task_id is None:
        task_id = str(uuid.uuid4())
    task = TaskRecord(
        task_id=task_id,
        module=module,
        status="queued",
        created_at=time.time(),
        payload=payload,
    )
    task_store[task_id] = task
    task_queue.put_nowait(task_id)
    return {"task_id": task_id, "status": "queued"}


@app.get("/")
async def index() -> FileResponse:
    page = STATIC_DIR / "index.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(str(page))


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "queue_size": task_queue.qsize(),
        "running_task_id": running_task_id,
    }


@app.get("/api/modules")
async def modules() -> Dict[str, Any]:
    return {
        "modules": [
            {"id": "voice_design", "name": "个性化语音（语音设计）"},
            {"id": "tts", "name": "语音生成（语音合成）"},
            {"id": "env_audio", "name": "环境音效（视频环境音）"},
        ]
    }


@app.post("/api/submit/voice-design")
async def submit_voice_design(
    text: str = Form(...),
    instruct: str = Form(""),
    language: str = Form("Chinese"),
) -> Dict[str, Any]:
    return enqueue_task("voice_design", {"text": text, "instruct": instruct, "language": language})


@app.post("/api/submit/tts")
async def submit_tts(
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
) -> Dict[str, Any]:
    task_id = str(uuid.uuid4())
    ref_path = save_upload(task_id, reference_audio, "tts")
    return enqueue_task(
        "tts",
        {
            "text_input": text_input,
            "emotion_happy": emotion_happy,
            "emotion_angry": emotion_angry,
            "emotion_sad": emotion_sad,
            "emotion_fear": emotion_fear,
            "emotion_disgust": emotion_disgust,
            "emotion_melancholy": emotion_melancholy,
            "emotion_surprise": emotion_surprise,
            "emotion_calm": emotion_calm,
            "use_random": use_random,
            "reference_audio_path": ref_path,
        },
        task_id=task_id,
    )


@app.post("/api/submit/env-audio")
async def submit_env_audio(
    prompt: str = Form(""),
    negative_prompt: str = Form(""),
    audio_mix_mode: str = Form("mix"),
    ambient_volume: str = Form("0.25"),
    bgm_volume: str = Form("0.3"),
    num_steps: str = Form("25"),
    cfg_strength: str = Form("4.5"),
    video: UploadFile = File(...),
) -> Dict[str, Any]:
    task_id = str(uuid.uuid4())
    video_path = save_upload(task_id, video, "env_audio")
    return enqueue_task(
        "env_audio",
        {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "audio_mix_mode": audio_mix_mode,
            "ambient_volume": ambient_volume,
            "bgm_volume": bgm_volume,
            "num_steps": num_steps,
            "cfg_strength": cfg_strength,
            "video_path": video_path,
        },
        task_id=task_id,
    )


@app.get("/api/task/{task_id}")
async def task_status(task_id: str) -> Dict[str, Any]:
    record = task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="task_id not found")
    data = json.loads(record.model_dump_json())
    if record.output_file:
        data["download_url"] = f"/api/download/{task_id}"
        data["output_file_name"] = Path(record.output_file).name
    return data


@app.get("/api/queue")
async def queue_status() -> Dict[str, Any]:
    totals = {"queued": 0, "running": 0, "done": 0, "failed": 0}
    for item in task_store.values():
        totals[item.status] += 1
    return {
        "queue_size": task_queue.qsize(),
        "running_task_id": running_task_id,
        "totals": totals,
    }


@app.get("/api/status")
async def status_alias() -> Dict[str, Any]:
    """联调别名接口，便于外部统一读取当前队列状态。"""
    totals = {"queued": 0, "running": 0, "done": 0, "failed": 0}
    for item in task_store.values():
        totals[item.status] += 1
    return {
        "ok": True,
        "queue_size": task_queue.qsize(),
        "running_task_id": running_task_id,
        "totals": totals,
    }


@app.post("/api/run/{app_name}")
async def run_alias(app_name: str, payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    """
    联调占位入口：
    - app1 / voice_design: 走真实语音设计队列
    - app2 / tts, app3 / env_audio: 返回已接收并提示使用 multipart 正式接口
    """
    name = app_name.lower().strip()
    if name in {"app1", "voice_design"}:
        text = str(payload.get("text", "")).strip()
        if not text:
            raise HTTPException(status_code=400, detail="app1/voice_design 需要 text 字段")
        instruct = str(payload.get("instruct", ""))
        language = str(payload.get("language", "Chinese"))
        result = enqueue_task("voice_design", {"text": text, "instruct": instruct, "language": language})
        return {
            "ok": True,
            "message": "已收到，排队中",
            "app": app_name,
            **result,
        }

    if name in {"app2", "tts", "app3", "env_audio"}:
        return {
            "ok": True,
            "message": "已收到。该应用需文件上传，请改用正式 multipart 接口",
            "app": app_name,
            "next": {
                "tts": "/api/submit/tts",
                "env_audio": "/api/submit/env-audio",
            },
        }

    raise HTTPException(status_code=404, detail=f"未知 app: {app_name}")


@app.get("/api/download/{task_id}")
async def download(task_id: str) -> FileResponse:
    record = task_store.get(task_id)
    if not record or not record.output_file:
        raise HTTPException(status_code=404, detail="output not found")
    out_file = Path(record.output_file)
    if not out_file.exists():
        raise HTTPException(status_code=404, detail="output file missing on disk")
    return FileResponse(str(out_file), filename=out_file.name)
