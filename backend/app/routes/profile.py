import json
import re
import asyncio
import shutil
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.config import PROFILES_DIR
from app.db import upsert_profile, update_status, get_profile_record, list_profiles, delete_profile_record
from app.analyzer.profile_builder import (
    extract_username, fetch_reel_urls, build_profile, save_profile, load_profile
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
async def list_all_profiles():
    return list_profiles()


@router.post("/connect")
async def connect_profile(req: ConnectRequest, background_tasks: BackgroundTasks):
    try:
        slug = extract_username(req.instagram_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    display_name = req.display_name or slug

    # Return existing completed profile from DB without re-running
    record = get_profile_record(slug)
    if record and record["status"] == "completed":
        existing = load_profile(slug)
        if existing and "error" not in existing.get("synthesis", {}) and existing.get("synthesis"):
            _write_state(slug, {"status": "completed", "step": "done", "progress": 0, "total": 0,
                                "reels_analyzed": existing.get("reels_analyzed", 0)})
            return {"username": slug, "status": "completed", "reel_urls": record["reel_urls"]}

    if req.reel_urls:
        preset_urls = _parse_instagram_urls(req.reel_urls)
        if not preset_urls:
            raise HTTPException(status_code=400, detail="No valid Instagram URLs found.")
        upsert_profile(slug, display_name, preset_urls, status="processing")
        _write_state(slug, {"status": "processing", "step": "downloading_reels", "progress": 0, "total": len(preset_urls)})
        background_tasks.add_task(_run_profile_build, slug, len(preset_urls), preset_urls)
    else:
        count = max(1, min(req.reel_count, 20))
        upsert_profile(slug, display_name, [], status="processing")
        _write_state(slug, {"status": "processing", "step": "fetching_urls", "progress": 0, "total": count})
        background_tasks.add_task(_run_profile_build, slug, count, None)

    return {"username": slug, "status": "processing"}


@router.get("/{slug}")
async def get_profile(slug: str):
    state = _read_state(slug)
    if not state:
        raise HTTPException(status_code=404, detail=f"No profile found for @{slug}")

    response = dict(state)
    if state.get("status") == "completed":
        profile = load_profile(slug)
        if profile:
            response["profile"] = profile

    record = get_profile_record(slug)
    if record:
        response["reel_urls"] = record["reel_urls"]
        response["display_name"] = record["display_name"]

    return response


@router.put("/{slug}/reels")
async def update_profile_reels(slug: str, req: UpdateReelsRequest, background_tasks: BackgroundTasks):
    """Update the URL set for a profile and re-synthesize."""
    record = get_profile_record(slug)
    if not record:
        raise HTTPException(status_code=404, detail=f"No profile found for @{slug}")

    urls = _parse_instagram_urls(req.reel_urls)
    if not urls:
        raise HTTPException(status_code=400, detail="No valid Instagram URLs found.")

    old_set = set(record["reel_urls"])
    new_set = set(urls)

    if new_set == old_set and record["status"] == "completed":
        # Nothing changed — return cached
        existing = load_profile(slug)
        if existing and "error" not in existing.get("synthesis", {}):
            return {"username": slug, "status": "completed", "cached": True}

    only_removals = new_set < old_set and record["status"] == "completed"
    if only_removals:
        # Reels removed but none added — synthesis is still valid, just update the URL list
        existing = load_profile(slug)
        if existing and "error" not in existing.get("synthesis", {}):
            upsert_profile(slug, record["display_name"], urls, status="completed")
            return {"username": slug, "status": "completed", "cached": True}

    # URLs added or synthesis was broken — clear and rebuild
    profile_json = PROFILES_DIR / slug / "profile.json"
    profile_json.unlink(missing_ok=True)

    upsert_profile(slug, record["display_name"], urls, status="processing")
    _write_state(slug, {"status": "processing", "step": "downloading_reels", "progress": 0, "total": len(urls)})
    background_tasks.add_task(_run_profile_build, slug, len(urls), urls)

    return {"username": slug, "status": "processing"}


@router.delete("/{slug}")
async def delete_profile(slug: str):
    profile_dir = PROFILES_DIR / slug
    if profile_dir.exists():
        shutil.rmtree(profile_dir)
    delete_profile_record(slug)
    return {"status": "deleted"}


async def _run_profile_build(username: str, count: int = 20, preset_urls: list[str] | None = None):
    try:
        if preset_urls:
            reel_urls = preset_urls
            total = len(reel_urls)
        else:
            _write_state(username, {"status": "processing", "step": "fetching_urls", "progress": 0, "total": count})
            reel_urls = await asyncio.to_thread(fetch_reel_urls, username, count)
            total = len(reel_urls)
            # Update DB with the discovered URLs
            record = get_profile_record(username)
            if record:
                upsert_profile(username, record["display_name"], reel_urls, status="processing")

        _write_state(username, {"status": "processing", "step": "downloading_reels", "progress": 0, "total": total})

        progress_state = {"done": 0, "completed_urls": []}

        def on_progress(completed: int, total: int, url: str):
            progress_state["done"] = completed
            progress_state["completed_urls"].append(url)
            _write_state(username, {
                "status": "processing",
                "step": "analyzing_reels",
                "progress": completed,
                "total": total,
                "current_url": url,
                "completed_urls": list(progress_state["completed_urls"]),
            })

        raw_profile = await asyncio.to_thread(build_profile, username, reel_urls, on_progress)

        _write_state(username, {"status": "processing", "step": "synthesizing_style", "progress": total, "total": total})

        style_profile = await asyncio.to_thread(synthesize_style_profile, username, raw_profile["reels"])
        style_profile["reels_analyzed"] = raw_profile["reels_analyzed"]
        style_profile["reels_failed"] = raw_profile["reels_failed"]

        save_profile(username, style_profile)
        update_status(username, "completed", raw_profile["reels_analyzed"])

        _write_state(username, {
            "status": "completed",
            "step": "done",
            "progress": total,
            "total": total,
            "reels_analyzed": raw_profile["reels_analyzed"],
        })

    except Exception as e:
        update_status(username, "error")
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
