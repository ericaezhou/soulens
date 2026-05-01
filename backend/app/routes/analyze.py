import json
import uuid
import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.models import AnalyzeRequest, JobStatus
from app.config import UPLOAD_DIR
from app.analyzer.downloader import download_reel
from app.analyzer.video import detect_scenes, analyze_pacing, analyze_motion
from app.analyzer.audio import analyze_audio
from app.analyzer.color import analyze_color_grade
from app.analyzer.text import detect_text_overlays
from app.analyzer.fingerprint import build_fingerprint

router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post("", response_model=JobStatus)
async def start_analysis(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    _write_job_state(job_dir, {"status": "processing", "job_id": job_id, "step": "queued"})
    background_tasks.add_task(_run_analysis, job_id, request.instagram_url, job_dir)

    return JobStatus(job_id=job_id, status="processing")


@router.get("/{job_id}", response_model=JobStatus)
async def get_analysis(job_id: str):
    job_dir = UPLOAD_DIR / job_id
    state_path = job_dir / "state.json"

    if not state_path.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    state = json.loads(state_path.read_text())
    return JobStatus(
        job_id=job_id,
        status=state.get("status", "processing"),
        result=state.get("result"),
        error=state.get("error"),
    )


async def _run_analysis(job_id: str, url: str, job_dir: Path):
    try:
        _update_step(job_dir, "downloading")
        video_meta = await asyncio.to_thread(download_reel, url, job_dir)

        video_path = video_meta["path"]

        _update_step(job_dir, "detecting_scenes")
        scenes = await asyncio.to_thread(detect_scenes, video_path)

        _update_step(job_dir, "analyzing_pacing")
        duration = video_meta.get("duration") or 30
        pacing = await asyncio.to_thread(analyze_pacing, scenes, duration)

        _update_step(job_dir, "analyzing_audio")
        audio = await asyncio.to_thread(analyze_audio, video_path)

        _update_step(job_dir, "analyzing_color")
        color = await asyncio.to_thread(analyze_color_grade, video_path, scenes)

        _update_step(job_dir, "detecting_text")
        text = await asyncio.to_thread(detect_text_overlays, video_path)

        _update_step(job_dir, "analyzing_motion")
        motion = await asyncio.to_thread(analyze_motion, video_path, scenes)

        _update_step(job_dir, "building_fingerprint")
        fingerprint = await asyncio.to_thread(
            build_fingerprint, scenes, pacing, audio, color, text, motion, video_meta
        )

        result = {
            "job_id": job_id,
            "fingerprint": fingerprint,
            "video_meta": video_meta,
        }

        _write_job_state(job_dir, {"status": "completed", "job_id": job_id, "result": result})

    except Exception as e:
        _write_job_state(job_dir, {
            "status": "error",
            "job_id": job_id,
            "error": str(e),
        })


def _update_step(job_dir: Path, step: str):
    state_path = job_dir / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    state["step"] = step
    state_path.write_text(json.dumps(state))


def _write_job_state(job_dir: Path, state: dict):
    (job_dir / "state.json").write_text(json.dumps(state))
