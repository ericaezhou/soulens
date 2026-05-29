import json
import re
import asyncio
import shutil
import threading
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from app.auth import require_auth
from pydantic import BaseModel

from app.config import PROFILES_DIR
from app.db import (
    upsert_profile, update_status, get_profile_record, list_profiles,
    delete_profile_record, save_profile_data, load_profile_data,
)
from app.analyzer.profile_builder import (
    extract_username, fetch_reel_urls, build_profile,
)
from app.analyzer.fingerprint import synthesize_style_profile

router = APIRouter(prefix="/profile", tags=["profile"])


class ConnectRequest(BaseModel):
    instagram_url: str
    display_name: str | None = None
    reel_count: int = 20
    reel_urls: list[str] | None = None


class UpdateReelsRequest(BaseModel):
    reel_urls: list[str]


def _parse_instagram_urls(raw: list[str]) -> list[str]:
    combined = " ".join(raw)
    found = re.findall(r'https?://(?:www\.)?instagram\.com/(?:p|reel)/[\w-]+/?', combined)
    return list(dict.fromkeys(found))


@router.get("")
async def list_all_profiles(user: dict = Depends(require_auth)):
    return list_profiles(user["sub"])


@router.post("/connect")
async def connect_profile(req: ConnectRequest, background_tasks: BackgroundTasks, user: dict = Depends(require_auth)):
    user_id = user["sub"]
    try:
        slug = extract_username(req.instagram_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    display_name = req.display_name or slug

    record = get_profile_record(user_id, slug)

    # Already waiting for user to trigger synthesis — don't restart analysis
    if record and record["status"] == "awaiting_synthesis":
        return {"username": slug, "status": "awaiting_synthesis", "reel_urls": record["reel_urls"]}

    # Return existing completed profile without re-running
    if record and record["status"] == "completed":
        existing = load_profile_data(user_id, slug)
        if existing and "error" not in existing.get("synthesis", {}) and existing.get("synthesis"):
            _write_state(slug, {"status": "completed", "step": "done", "progress": 0, "total": 0,
                                "reels_analyzed": existing.get("reels_analyzed", 0)})
            return {"username": slug, "status": "completed", "reel_urls": record["reel_urls"]}

    if req.reel_urls:
        preset_urls = _parse_instagram_urls(req.reel_urls)
        if not preset_urls:
            raise HTTPException(status_code=400, detail="No valid Instagram URLs found.")
        try:
            upsert_profile(user_id, slug, display_name, preset_urls, status="processing")
        except ValueError as e:
            raise HTTPException(status_code=403, detail=str(e))
        _write_state(slug, {"status": "processing", "step": "analyzing_reels", "progress": 0, "total": len(preset_urls)})
        background_tasks.add_task(_run_profile_build, user_id, slug, len(preset_urls), preset_urls)
    else:
        count = max(1, min(req.reel_count, 20))
        try:
            upsert_profile(user_id, slug, display_name, [], status="processing")
        except ValueError as e:
            raise HTTPException(status_code=403, detail=str(e))
        _write_state(slug, {"status": "processing", "step": "fetching_urls", "progress": 0, "total": count})
        background_tasks.add_task(_run_profile_build, user_id, slug, count, None)

    return {"username": slug, "status": "processing"}


@router.get("/{slug}")
async def get_profile(slug: str, user: dict = Depends(require_auth)):
    user_id = user["sub"]
    state = _read_state(slug)

    if not state:
        # State file missing (e.g. after Railway redeploy) — reconstruct from DB
        record = get_profile_record(user_id, slug)
        if not record:
            raise HTTPException(status_code=404, detail=f"No profile found for @{slug}")
        if record["status"] == "completed":
            profile_data = load_profile_data(user_id, slug)
            return {
                "status": "completed",
                "step": "done",
                "progress": record.get("reels_analyzed", 0),
                "total": record.get("reels_analyzed", 0),
                "reels_analyzed": record.get("reels_analyzed", 0),
                "reel_urls": record["reel_urls"],
                "display_name": record["display_name"],
                "profile": profile_data,
            }
        return {
            "status": record["status"],
            "step": "unknown",
            "progress": 0,
            "total": 0,
            "reel_urls": record["reel_urls"],
            "display_name": record["display_name"],
        }

    response = dict(state)
    if state.get("status") == "completed":
        profile_data = load_profile_data(user_id, slug)
        if profile_data:
            response["profile"] = profile_data

    record = get_profile_record(user_id, slug)
    if record:
        response["reel_urls"] = record["reel_urls"]
        response["display_name"] = record["display_name"]

    return response


@router.put("/{slug}/reels")
async def update_profile_reels(slug: str, req: UpdateReelsRequest, background_tasks: BackgroundTasks, user: dict = Depends(require_auth)):
    """Update the URL set for a profile and re-analyze (pauses before synthesis)."""
    user_id = user["sub"]
    record = get_profile_record(user_id, slug)
    if not record:
        raise HTTPException(status_code=404, detail=f"No profile found for @{slug}")

    urls = _parse_instagram_urls(req.reel_urls)
    if not urls:
        raise HTTPException(status_code=400, detail="No valid Instagram URLs found.")

    old_set = set(record["reel_urls"])
    new_set = set(urls)

    # Same URLs and already awaiting synthesis — just return that state
    if new_set == old_set and record["status"] == "awaiting_synthesis":
        return {"username": slug, "status": "awaiting_synthesis", "cached": True}

    # Same URLs and already completed — return cached synthesis
    if new_set == old_set and record["status"] == "completed":
        existing = load_profile_data(user_id, slug)
        if existing and "error" not in existing.get("synthesis", {}):
            return {"username": slug, "status": "completed", "cached": True}

    # Removals only from a completed profile — synthesis still valid, just update URL list
    only_removals = new_set < old_set and record["status"] == "completed"
    if only_removals:
        existing = load_profile_data(user_id, slug)
        if existing and "error" not in existing.get("synthesis", {}):
            upsert_profile(user_id, slug, record["display_name"], urls, status="completed")
            return {"username": slug, "status": "completed", "cached": True}

    # New URLs added (or prior synthesis failed) — re-analyze
    upsert_profile(user_id, slug, record["display_name"], urls, status="processing")
    _write_state(slug, {"status": "processing", "step": "analyzing_reels", "progress": 0, "total": len(urls)})
    background_tasks.add_task(_run_profile_build, user_id, slug, len(urls), urls)

    return {"username": slug, "status": "processing"}


@router.post("/{slug}/synthesize")
async def synthesize_profile(slug: str, background_tasks: BackgroundTasks, user: dict = Depends(require_auth)):
    """Trigger Claude synthesis after the user confirms (this is where API credits are used)."""
    user_id = user["sub"]
    state = _read_state(slug)
    if not state or state.get("status") != "awaiting_synthesis":
        raise HTTPException(status_code=400, detail="Profile is not awaiting synthesis")

    raw_path = PROFILES_DIR / slug / "raw_profile.json"
    if not raw_path.exists():
        raise HTTPException(status_code=400, detail="Raw analysis data not found — please re-analyze")

    total = state.get("total", 0)
    update_status(user_id, slug, "processing")
    _write_state(slug, {
        "status": "processing",
        "step": "synthesizing_style",
        "progress": total,
        "total": total,
    })
    background_tasks.add_task(_run_synthesis, user_id, slug)
    return {"username": slug, "status": "processing"}


@router.delete("/{slug}")
async def delete_profile(slug: str, user: dict = Depends(require_auth)):
    user_id = user["sub"]
    profile_dir = PROFILES_DIR / slug
    if profile_dir.exists():
        shutil.rmtree(profile_dir)
    delete_profile_record(user_id, slug)
    return {"status": "deleted"}


async def _run_profile_build(user_id: str, username: str, count: int = 20, preset_urls: list[str] | None = None):
    try:
        if preset_urls:
            reel_urls = preset_urls
            total = len(reel_urls)
        else:
            _write_state(username, {"status": "processing", "step": "fetching_urls", "progress": 0, "total": count})
            reel_urls = await asyncio.to_thread(fetch_reel_urls, username, count)
            total = len(reel_urls)
            record = get_profile_record(user_id, username)
            if record:
                upsert_profile(user_id, username, record["display_name"], reel_urls, status="processing")

        _write_state(username, {"status": "processing", "step": "analyzing_reels", "progress": 0, "total": total})

        progress_state: dict = {"done": 0, "log": []}
        active_tasks: dict = {}
        state_lock = threading.Lock()

        def _flush_state():
            with state_lock:
                _write_state(username, {
                    "status": "processing",
                    "step": "analyzing_reels",
                    "progress": progress_state["done"],
                    "total": total,
                    "log": list(progress_state["log"]),
                    "active_tasks": dict(active_tasks),
                })

        def on_step(shortcode: str, step: str):
            active_tasks[shortcode] = step
            _flush_state()

        def on_progress(completed: int, total: int, url: str, result: dict):
            shortcode = url.rstrip("/").split("/")[-1]
            active_tasks.pop(shortcode, None)
            if "error" in result:
                entry = {"shortcode": shortcode, "error": result["error"]}
            else:
                entry = {
                    "shortcode": shortcode,
                    "duration_s": round(result.get("meta", {}).get("duration") or 0),
                    "cuts": result.get("pacing", {}).get("cut_count", 0),
                    "has_speech": result.get("transcript", {}).get("has_speech", False),
                    "word_count": result.get("transcript", {}).get("word_count", 0),
                }
            progress_state["done"] = completed
            progress_state["log"].append(entry)
            _flush_state()

        raw_profile = await asyncio.to_thread(build_profile, username, reel_urls, on_progress, on_step)

        # Persist raw analysis so synthesis can be triggered later
        raw_path = PROFILES_DIR / username / "raw_profile.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(raw_profile))

        # Pause here — user must confirm before API credits are spent
        update_status(user_id, username, "awaiting_synthesis")
        _write_state(username, {
            "status": "awaiting_synthesis",
            "step": "ready",
            "progress": total,
            "total": total,
            "reels_analyzed": raw_profile["reels_analyzed"],
            "reels_failed": raw_profile["reels_failed"],
        })

    except Exception as e:
        update_status(user_id, username, "error")
        _write_state(username, {"status": "error", "error": str(e)})


async def _run_synthesis(user_id: str, username: str):
    try:
        raw_path = PROFILES_DIR / username / "raw_profile.json"
        raw_profile = json.loads(raw_path.read_text())
        total = raw_profile.get("reels_analyzed", 0) + raw_profile.get("reels_failed", 0)

        style_profile = await asyncio.to_thread(synthesize_style_profile, username, raw_profile["reels"])
        style_profile["reels_analyzed"] = raw_profile["reels_analyzed"]
        style_profile["reels_failed"] = raw_profile["reels_failed"]

        save_profile_data(user_id, username, style_profile)
        update_status(user_id, username, "completed", raw_profile["reels_analyzed"])
        _write_state(username, {
            "status": "completed",
            "step": "done",
            "progress": total,
            "total": total,
            "reels_analyzed": raw_profile["reels_analyzed"],
        })

    except Exception as e:
        update_status(user_id, username, "error")
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
