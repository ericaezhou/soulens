import json
import uuid
import asyncio
import subprocess
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse

from app.config import UPLOAD_DIR
from app.analyzer.profile_builder import load_profile
from app.analyzer.video import detect_scenes
from app.analyzer.scriptwriter import generate_script_and_captions
from app.editor.engine import apply_style
from app.editor.rough_cut import run_rough_cut

router = APIRouter(prefix="/edit", tags=["edit"])


@router.post("/upload")
async def upload_footage(files: list[UploadFile] = File(...)):
    job_id = str(uuid.uuid4())
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for i, f in enumerate(files):
        ext = Path(f.filename or "video.mp4").suffix or ".mp4"
        p = job_dir / f"clip_{i:02d}{ext}"
        p.write_bytes(await f.read())
        saved.append(p)

    if len(saved) == 1:
        footage_path = saved[0]
    else:
        footage_path = await asyncio.to_thread(_concat_clips, saved, job_dir)

    _write_state(job_dir, {"status": "ready", "job_id": job_id, "footage_path": str(footage_path), "clip_count": len(saved)})
    return {"job_id": job_id, "status": "ready", "clip_count": len(saved)}


@router.post("/start")
async def start_edit(
    background_tasks: BackgroundTasks,
    username: str = Form(...),
    footage_job_id: str = Form(...),
    topic: str = Form(""),
    skip_script: bool = Form(False),
):
    # Validate profile exists
    profile = load_profile(username)
    if not profile:
        raise HTTPException(status_code=404, detail=f"No style profile found for @{username}. Connect the profile first.")

    # Validate footage exists
    footage_state_path = UPLOAD_DIR / footage_job_id / "state.json"
    if not footage_state_path.exists():
        raise HTTPException(status_code=404, detail="Footage job not found")

    footage_state = json.loads(footage_state_path.read_text())
    footage_path = footage_state.get("footage_path")
    if not footage_path or not Path(footage_path).exists():
        raise HTTPException(status_code=404, detail="Footage file not found")

    edit_job_id = str(uuid.uuid4())
    edit_dir = UPLOAD_DIR / edit_job_id
    edit_dir.mkdir(parents=True, exist_ok=True)
    _write_state(edit_dir, {"status": "processing", "job_id": edit_job_id, "step": "analyzing_footage"})

    background_tasks.add_task(_run_edit, edit_job_id, footage_path, profile, topic, edit_dir)
    return {"job_id": edit_job_id, "status": "processing"}


@router.get("/status/{job_id}")
async def edit_status(job_id: str):
    state_path = UPLOAD_DIR / job_id / "state.json"
    if not state_path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return json.loads(state_path.read_text())


@router.get("/download/{job_id}/video")
async def download_video(job_id: str):
    return _download_file(job_id, "mp4_path", "video/mp4", f"auto-edit-{job_id[:8]}.mp4")


@router.get("/download/{job_id}/fcpxml")
async def download_fcpxml(job_id: str):
    return _download_file(job_id, "fcpxml_path", "application/xml", f"auto-edit-{job_id[:8]}.fcpxml")


@router.get("/download/{job_id}/script")
async def download_script(job_id: str):
    state = _get_completed_state(job_id)
    script = state.get("result", {}).get("script", {})
    if not script:
        raise HTTPException(status_code=404, detail="No script available")

    # Build a readable text file
    lines = []
    spoken = script.get("spoken_script", {})
    if spoken:
        lines += [
            "=== HOOK ===",
            spoken.get("hook", ""),
            "",
            "=== BODY ===",
            spoken.get("body", ""),
            "",
            "=== CTA ===",
            spoken.get("cta", ""),
            "",
            "=== FULL SCRIPT ===",
            spoken.get("full_script", ""),
            "",
            f"TONE: {spoken.get('tone_notes', '')}",
            "",
        ]
    lines += [
        "=== INSTAGRAM CAPTION ===",
        script.get("reel_caption", ""),
        "",
        "=== HASHTAGS ===",
        " ".join(script.get("hashtag_suggestions", [])),
    ]

    content = "\n".join(lines)
    script_path = UPLOAD_DIR / job_id / "script.txt"
    script_path.write_text(content)

    return FileResponse(str(script_path), media_type="text/plain", filename=f"script-{job_id[:8]}.txt")


def _download_file(job_id: str, path_key: str, media_type: str, filename: str) -> FileResponse:
    state = _get_completed_state(job_id)
    file_path = state.get("result", {}).get(path_key)
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type=media_type, filename=filename)


def _get_completed_state(job_id: str) -> dict:
    state_path = UPLOAD_DIR / job_id / "state.json"
    if not state_path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    state = json.loads(state_path.read_text())
    if state.get("status") != "completed":
        raise HTTPException(status_code=400, detail=f"Edit not complete (status: {state.get('status')})")
    return state


async def _run_edit(job_id: str, footage_path: str, profile: dict, topic: str, edit_dir: Path):
    try:
        # Step 1: detect scenes + universal rough cut (free, no API)
        _write_state(edit_dir, {"status": "processing", "job_id": job_id, "step": "rough_cut"})

        probe_cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", footage_path]
        probe = subprocess.run(probe_cmd, capture_output=True, text=True)
        duration = 30.0
        if probe.returncode == 0:
            duration = float(json.loads(probe.stdout).get("format", {}).get("duration", 30))

        scenes = await asyncio.to_thread(detect_scenes, footage_path)
        rough = await asyncio.to_thread(run_rough_cut, footage_path, scenes)

        _write_state(edit_dir, {
            "status": "processing", "job_id": job_id, "step": "rough_cut_done",
            "rough_cut": {
                "total_scenes": rough["total_scenes"],
                "candidate_count": rough["candidate_count"],
                "rejected_count": rough["rejected_count"],
                "candidate_duration_s": rough["candidate_duration_s"],
                "retention_pct": rough["retention_pct"],
                "rejection_summary": rough["rejection_summary"],
            },
        })

        candidate_clips = rough["candidates"]

        # Step 2: generate script + caption plan
        _write_state(edit_dir, {"status": "processing", "job_id": job_id, "step": "generating_script"})
        script = await asyncio.to_thread(
            generate_script_and_captions, profile, scenes, duration, topic
        )
        caption_plan = script.get("caption_plan") if isinstance(script, dict) else None

        # Step 3: render video + fcpxml using rough cut candidates
        _write_state(edit_dir, {"status": "processing", "job_id": job_id, "step": "rendering"})
        edit_result = await asyncio.to_thread(
            apply_style, footage_path, profile, edit_dir, caption_plan, candidate_clips
        )

        _write_state(edit_dir, {
            "status": "completed",
            "job_id": job_id,
            "result": {**edit_result, "script": script, "rough_cut": rough},
        })

    except Exception as e:
        _write_state(edit_dir, {"status": "error", "job_id": job_id, "error": str(e)})


def _concat_clips(clips: list[Path], job_dir: Path) -> Path:
    """Concatenate clips in order using ffmpeg concat demuxer. Falls back to re-encode if needed."""
    list_path = job_dir / "clips.txt"
    list_path.write_text("\n".join(f"file '{p.resolve()}'" for p in clips))

    out_path = job_dir / "footage.mp4"
    # Try stream-copy first (instant, no quality loss); -fflags +genpts fixes iPhone MOV timestamp offsets
    cmd = ["ffmpeg", "-fflags", "+genpts", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_path), "-y"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Fall back to re-encode (handles mismatched codecs/resolutions)
        cmd = [
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k", str(out_path), "-y",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to concatenate clips: {result.stderr[-500:]}")

    return out_path


def _write_state(job_dir: Path, state: dict):
    (job_dir / "state.json").write_text(json.dumps(state))
