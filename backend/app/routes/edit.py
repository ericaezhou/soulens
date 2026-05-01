import json
import uuid
import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from app.config import UPLOAD_DIR
from app.editor.engine import apply_style

router = APIRouter(prefix="/edit", tags=["edit"])


@router.post("/upload")
async def upload_footage(file: UploadFile = File(...)):
    """Upload raw footage to edit."""
    job_id = str(uuid.uuid4())
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "video.mp4").suffix or ".mp4"
    footage_path = job_dir / f"footage{ext}"

    content = await file.read()
    footage_path.write_bytes(content)

    state = {"status": "ready", "job_id": job_id, "footage_path": str(footage_path)}
    (job_dir / "state.json").write_text(json.dumps(state))

    return {"job_id": job_id, "status": "ready", "filename": file.filename}


@router.post("/apply")
async def apply_edit(
    background_tasks: BackgroundTasks,
    style_job_id: str = Form(...),
    footage_job_id: str = Form(...),
):
    """Apply a style fingerprint to uploaded footage."""
    # Load style fingerprint
    style_dir = UPLOAD_DIR / style_job_id
    style_state_path = style_dir / "state.json"
    if not style_state_path.exists():
        raise HTTPException(status_code=404, detail="Style job not found")

    style_state = json.loads(style_state_path.read_text())
    if style_state.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Style analysis not complete")

    fingerprint = style_state["result"]["fingerprint"]

    # Load footage
    footage_dir = UPLOAD_DIR / footage_job_id
    footage_state_path = footage_dir / "state.json"
    if not footage_state_path.exists():
        raise HTTPException(status_code=404, detail="Footage job not found")

    footage_state = json.loads(footage_state_path.read_text())
    footage_path = footage_state.get("footage_path")
    if not footage_path or not Path(footage_path).exists():
        raise HTTPException(status_code=404, detail="Footage file not found")

    # Create edit job
    edit_job_id = str(uuid.uuid4())
    edit_dir = UPLOAD_DIR / edit_job_id
    edit_dir.mkdir(parents=True, exist_ok=True)
    (edit_dir / "state.json").write_text(json.dumps({"status": "processing", "job_id": edit_job_id}))

    background_tasks.add_task(_run_edit, edit_job_id, footage_path, fingerprint, edit_dir)

    return {"job_id": edit_job_id, "status": "processing"}


@router.get("/status/{job_id}")
async def edit_status(job_id: str):
    state_path = UPLOAD_DIR / job_id / "state.json"
    if not state_path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return json.loads(state_path.read_text())


@router.get("/download/{job_id}")
async def download_edit(job_id: str):
    state_path = UPLOAD_DIR / job_id / "state.json"
    if not state_path.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    state = json.loads(state_path.read_text())
    if state.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Edit not complete")

    output_path = state.get("result", {}).get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"auto-edit-{job_id[:8]}.mp4",
    )


async def _run_edit(job_id: str, footage_path: str, fingerprint: dict, edit_dir: Path):
    try:
        result = await asyncio.to_thread(apply_style, footage_path, fingerprint, edit_dir)
        state = {"status": "completed", "job_id": job_id, "result": result}
    except Exception as e:
        state = {"status": "error", "job_id": job_id, "error": str(e)}

    (edit_dir / "state.json").write_text(json.dumps(state))
