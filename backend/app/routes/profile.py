import json
import asyncio
import uuid
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.config import PROFILES_DIR, UPLOAD_DIR
from app.analyzer.profile_builder import (
    extract_username, fetch_reel_urls, build_profile, save_profile, load_profile
)
from app.analyzer.fingerprint import synthesize_style_profile

router = APIRouter(prefix="/profile", tags=["profile"])


class ConnectRequest(BaseModel):
    instagram_url: str
    reel_count: int = 20


@router.post("/connect")
async def connect_profile(req: ConnectRequest, background_tasks: BackgroundTasks):
    try:
        username = extract_username(req.instagram_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    count = max(1, min(req.reel_count, 20))

    # Write initial state
    state_path = PROFILES_DIR / username / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    _write_state(username, {"status": "processing", "step": "fetching_urls", "progress": 0, "total": count})

    background_tasks.add_task(_run_profile_build, username, count)

    return {"username": username, "status": "processing"}


@router.get("/{username}")
async def get_profile(username: str):
    state = _read_state(username)
    if not state:
        raise HTTPException(status_code=404, detail=f"No profile found for @{username}")

    response = dict(state)

    if state.get("status") == "completed":
        profile = load_profile(username)
        if profile:
            response["profile"] = profile

    return response


@router.delete("/{username}")
async def delete_profile(username: str):
    profile_dir = PROFILES_DIR / username
    if profile_dir.exists():
        shutil.rmtree(profile_dir)
    return {"status": "deleted"}


async def _run_profile_build(username: str, count: int = 20):
    try:
        # Step 1: fetch reel URLs
        _write_state(username, {"status": "processing", "step": "fetching_urls", "progress": 0, "total": count})
        reel_urls = await asyncio.to_thread(fetch_reel_urls, username, count)
        total = len(reel_urls)
        _write_state(username, {"status": "processing", "step": "downloading_reels", "progress": 0, "total": total})

        # Step 2: analyze each reel (with progress updates)
        progress_state = {"done": 0}

        def on_progress(completed: int, total: int, url: str):
            progress_state["done"] = completed
            _write_state(username, {
                "status": "processing",
                "step": "analyzing_reels",
                "progress": completed,
                "total": total,
                "current_url": url,
            })

        raw_profile = await asyncio.to_thread(build_profile, username, reel_urls, on_progress)

        # Step 3: Claude synthesizes all reels into Style Profile
        _write_state(username, {
            "status": "processing",
            "step": "synthesizing_style",
            "progress": total,
            "total": total,
        })

        style_profile = await asyncio.to_thread(
            synthesize_style_profile, username, raw_profile["reels"]
        )

        # Attach summary counts
        style_profile["reels_analyzed"] = raw_profile["reels_analyzed"]
        style_profile["reels_failed"] = raw_profile["reels_failed"]

        save_profile(username, style_profile)

        _write_state(username, {
            "status": "completed",
            "step": "done",
            "progress": total,
            "total": total,
            "reels_analyzed": raw_profile["reels_analyzed"],
        })

    except Exception as e:
        _write_state(username, {"status": "error", "error": str(e)})


def _write_state(username: str, state: dict):
    path = PROFILES_DIR / username / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def _read_state(username: str) -> dict | None:
    path = PROFILES_DIR / username / "state.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
