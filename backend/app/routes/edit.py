import json
import uuid
import base64
import asyncio
import subprocess
import zipfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks, Depends
from app.auth import require_auth
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from app.config import UPLOAD_DIR
from app.db import load_profile_data
from app.analyzer.scriptwriter import generate_script_and_captions
from app.analyzer.cataloger import catalog_clips
from app.analyzer.paper_edit import plan_edit
from app.analyzer.precision_trim import trim_scenes
from app.analyzer.frames import grab_frame
from app.editor.fcpxml import generate_fcpxml
from app.editor.rough_cut import score_clip, compute_global_threshold, build_clip_candidates
from app.storage import upload_output

router = APIRouter(prefix="/edit", tags=["edit"])


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_footage(files: list[UploadFile] = File(...)):
    job_id = str(uuid.uuid4())
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for i, f in enumerate(files):
        ext = Path(f.filename or "video.mp4").suffix or ".mp4"
        p = job_dir / f"raw_{i:02d}{ext}"
        p.write_bytes(await f.read())
        saved.append((i, p))

    clip_paths = []
    for i, src in saved:
        remuxed = await asyncio.to_thread(_remux_to_mp4, src, job_dir, i)
        clip_paths.append(str(remuxed))

    _write_state(job_dir, {
        "status": "ready",
        "job_id": job_id,
        "clip_paths": clip_paths,
        "clip_count": len(clip_paths),
    })
    return {"job_id": job_id, "status": "ready", "clip_count": len(clip_paths)}


# ── Start edit ────────────────────────────────────────────────────────────────

@router.post("/start")
async def start_edit(
    background_tasks: BackgroundTasks,
    username: str = Form(...),
    footage_job_id: str = Form(...),
    topic: str = Form(""),
    skip_script: bool = Form(False),
    user: dict = Depends(require_auth),
):
    user_id = user["sub"]
    profile = load_profile_data(user_id, username)
    if not profile:
        raise HTTPException(404, f"No style profile found for @{username}.")

    footage_state_path = UPLOAD_DIR / footage_job_id / "state.json"
    if not footage_state_path.exists():
        raise HTTPException(404, "Footage job not found")

    footage_state = json.loads(footage_state_path.read_text())
    clip_paths = footage_state.get("clip_paths")
    if not clip_paths:
        legacy = footage_state.get("footage_path")
        if legacy and Path(legacy).exists():
            clip_paths = [legacy]
    if not clip_paths:
        raise HTTPException(404, "Footage files not found")

    for p in clip_paths:
        if not Path(p).exists():
            raise HTTPException(404, f"Clip file missing: {Path(p).name}")

    edit_job_id = str(uuid.uuid4())
    edit_dir = UPLOAD_DIR / edit_job_id
    edit_dir.mkdir(parents=True, exist_ok=True)
    _write_state(edit_dir, {"status": "processing", "job_id": edit_job_id, "step": "starting"})

    background_tasks.add_task(
        _run_rough_cut,
        edit_job_id, clip_paths, profile, topic, edit_dir, skip_script, user_id,
    )
    return {"job_id": edit_job_id, "status": "processing"}


# ── Proceed past rough cut → Phase 1 + Phase 2 ───────────────────────────────

@router.post("/proceed/{job_id}")
async def proceed_edit(job_id: str, background_tasks: BackgroundTasks):
    state_path = UPLOAD_DIR / job_id / "state.json"
    if not state_path.exists():
        raise HTTPException(404, "Job not found")

    state = json.loads(state_path.read_text())
    if state.get("status") != "awaiting_rough_cut_review":
        raise HTTPException(400, f"Job is not awaiting rough cut review (status: {state.get('status')})")

    edit_dir = UPLOAD_DIR / job_id
    _write_state(edit_dir, {
        "status": "processing",
        "job_id": job_id,
        "step": "cataloging",
        "rough_cut": state.get("rough_cut"),
        "_config": state.get("_config"),
        "_clip_paths": state.get("_clip_paths"),
    })

    background_tasks.add_task(_run_phase1_and_phase2, job_id, edit_dir)
    return {"status": "processing"}


# ── Confirm scenes (user approved the paper edit) → Phase 3 ──────────────────

class ConfirmScenesRequest(BaseModel):
    scene_ids: list[str]


@router.post("/confirm_scenes/{job_id}")
async def confirm_scenes(job_id: str, body: ConfirmScenesRequest, background_tasks: BackgroundTasks):
    state_path = UPLOAD_DIR / job_id / "state.json"
    if not state_path.exists():
        raise HTTPException(404, "Job not found")

    state = json.loads(state_path.read_text())
    if state.get("status") != "awaiting_paper_edit_review":
        raise HTTPException(400, f"Job is not awaiting scene confirmation (status: {state.get('status')})")

    if not body.scene_ids:
        raise HTTPException(400, "scene_ids must not be empty")

    edit_dir = UPLOAD_DIR / job_id
    _write_state(edit_dir, {
        "status": "processing",
        "job_id": job_id,
        "step": "trimming_cuts",
        "rough_cut": state.get("rough_cut"),
        "_config": state.get("_config"),
        "_approved_scene_ids": body.scene_ids,
    })

    background_tasks.add_task(_run_phase3, job_id, edit_dir)
    return {"status": "processing"}


# ── Finalize: render after user approves detailed cuts ────────────────────────

class FinalizeRequest(BaseModel):
    drop: list[int] = []


@router.post("/finalize/{job_id}")
async def finalize_edit(job_id: str, body: FinalizeRequest, background_tasks: BackgroundTasks):
    state_path = UPLOAD_DIR / job_id / "state.json"
    if not state_path.exists():
        raise HTTPException(404, "Job not found")

    state = json.loads(state_path.read_text())
    if state.get("status") != "awaiting_detailed_cut_review":
        raise HTTPException(400, f"Job is not awaiting finalization (status: {state.get('status')})")

    config = state.get("_config", {})
    profile = load_profile_data(config.get("user_id", ""), config.get("username", ""))
    if not profile:
        raise HTTPException(404, "Profile no longer found")

    detailed_cuts = state.get("detailed_cuts", [])
    edit_dir = UPLOAD_DIR / job_id
    _write_state(edit_dir, {"status": "processing", "job_id": job_id, "step": "building_selects"})

    background_tasks.add_task(
        _render_edit,
        job_id, edit_dir, profile,
        detailed_cuts, body.drop,
        config.get("topic", ""),
        config.get("skip_script", True),
    )
    return {"status": "processing"}


# ── AI Refinement loop ───────────────────────────────────────────────────────

class ReplanRequest(BaseModel):
    feedback: str = ""
    current_scene_ids: list[str] | None = None  # current user selection (overrides disk manifest)


@router.post("/replan/{job_id}")
async def replan_edit(job_id: str, body: ReplanRequest, user: dict = Depends(require_auth)):
    """Re-run Phase 2 with user feedback. Returns updated manifest without changing job state."""
    edit_dir = UPLOAD_DIR / job_id
    catalog_path = edit_dir / "catalog.json"
    manifest_scenes_path = edit_dir / "manifest_scenes.json"

    if not catalog_path.exists() or not manifest_scenes_path.exists():
        raise HTTPException(404, "Edit data not found — please start a new edit")

    # No feedback → return current manifest unchanged (no API credits spent)
    if not body.feedback.strip():
        manifest_path = edit_dir / "manifest_v2.json"
        if manifest_path.exists():
            return json.loads(manifest_path.read_text())
        raise HTTPException(404, "Manifest not found")

    state = json.loads((edit_dir / "state.json").read_text())
    config = state.get("_config", {})
    profile = load_profile_data(user["sub"], config.get("username", ""))
    if not profile:
        raise HTTPException(404, "Style profile not found")

    scenes = json.loads(catalog_path.read_text())["scenes"]
    manifest_scenes = json.loads(manifest_scenes_path.read_text())

    # Build current_selection from user's actual scene IDs if provided,
    # otherwise fall back to the saved manifest on disk
    current_manifest = None
    if body.current_scene_ids is not None:
        # Rebuild selection from manifest_scenes filtered by what the user has selected
        id_set = set(body.current_scene_ids)
        kept = [s for s in manifest_scenes if s["scene_id"] in id_set and not s["scene_id"].endswith("_hook")]
        dropped_ids_set = {s["scene_id"] for s in manifest_scenes if s["scene_id"] not in id_set and not s["scene_id"].endswith("_hook")}
        current_manifest = {
            "hook_scene_id": next((sid for sid in body.current_scene_ids if sid.endswith("_hook")), "").replace("_hook", ""),
            "scenes": [{"scene_id": s["scene_id"]} for s in kept],
        }
    else:
        manifest_path = edit_dir / "manifest_v2.json"
        if manifest_path.exists():
            current_manifest = json.loads(manifest_path.read_text())

    paper_edit = await asyncio.to_thread(plan_edit, scenes, profile, body.feedback, current_manifest)

    hook_id: str = paper_edit.get("hook_scene_id", "")
    dropped_ids: set[str] = set(paper_edit.get("drop", []))

    def _sort_key(s: dict) -> tuple:
        try:
            parts = s["scene_id"].split("_")
            return (int(parts[1]), int(parts[3]))
        except (IndexError, ValueError):
            return (s.get("clip_index", 0), 0)

    kept = sorted([s for s in manifest_scenes if s["scene_id"] not in dropped_ids], key=_sort_key)
    hook_scene = next((s for s in kept if s["scene_id"] == hook_id), None)
    ordered = ([{**hook_scene, "scene_id": f"{hook_id}_hook", "is_hook": True}] + kept) if hook_scene else kept
    ui_scenes = [{k: v for k, v in s.items() if k != "clip_path"} for s in ordered]

    dropped_scenes_ui = [
        {k: v for k, v in s.items() if k != "clip_path"}
        for s in manifest_scenes if s["scene_id"] in dropped_ids
    ]

    return {
        "narrative_summary": paper_edit.get("narrative_summary", ""),
        "reasoning": paper_edit.get("reasoning", ""),
        "hook_scene_id": hook_id,
        "scenes": ui_scenes,
        "dropped_scenes": dropped_scenes_ui,
        "dropped_scene_count": len(dropped_ids),
        "feedback_used": body.feedback.strip(),
    }


# ── Status / download ─────────────────────────────────────────────────────────

@router.get("/status/{job_id}")
async def edit_status(job_id: str):
    state_path = UPLOAD_DIR / job_id / "state.json"
    if not state_path.exists():
        raise HTTPException(404, "Job not found")
    return json.loads(state_path.read_text())


@router.get("/download/{job_id}/video")
async def download_video(job_id: str):
    return _download_file(job_id, "mp4_path", "video/mp4", f"auto-edit-{job_id[:8]}.mp4")


@router.get("/download/{job_id}/fcpxml")
async def download_fcpxml(job_id: str):
    return _download_file(job_id, "fcpxml_path", "application/xml", f"auto-edit-{job_id[:8]}.fcpxml")


@router.get("/download/{job_id}/srt")
async def download_srt(job_id: str):
    return _download_file(job_id, "srt_path", "text/plain", f"captions-{job_id[:8]}.srt")


@router.get("/download/{job_id}/script")
async def download_script(job_id: str):
    state = _get_completed_state(job_id)
    script = state.get("result", {}).get("script", {})
    if not script:
        raise HTTPException(404, "No script available")

    lines = []
    spoken = script.get("spoken_script", {})
    if spoken:
        lines += [
            "=== HOOK ===", spoken.get("hook", ""), "",
            "=== BODY ===", spoken.get("body", ""), "",
            "=== CTA ===", spoken.get("cta", ""), "",
            "=== FULL SCRIPT ===", spoken.get("full_script", ""), "",
            f"TONE: {spoken.get('tone_notes', '')}", "",
        ]
    lines += [
        "=== INSTAGRAM CAPTION ===", script.get("reel_caption", ""), "",
        "=== HASHTAGS ===", " ".join(script.get("hashtag_suggestions", [])),
    ]

    script_path = UPLOAD_DIR / job_id / "script.txt"
    script_path.write_text("\n".join(lines))
    return FileResponse(str(script_path), media_type="text/plain", filename=f"script-{job_id[:8]}.txt")


# ── Pipeline: rough cut → pause for review ────────────────────────────────────

async def _run_rough_cut(
    job_id: str,
    clip_paths: list[str],
    profile: dict,
    topic: str,
    edit_dir: Path,
    skip_script: bool,
    user_id: str = "",
):
    try:
        _write_state(edit_dir, {"status": "processing", "job_id": job_id, "step": "rough_cut"})

        score_results = await asyncio.gather(*[
            asyncio.to_thread(score_clip, p) for p in clip_paths
        ])
        scored = [(clip_paths[i], score_results[i][0], score_results[i][1]) for i in range(len(clip_paths))]

        global_threshold = compute_global_threshold([w for _, w, _ in scored])

        clip_summaries = []
        candidates_by_clip: dict[int, list] = {}

        for i, (clip_path, windows, duration_clip) in enumerate(scored):
            if not windows:
                clip_summaries.append({
                    "clip_index": i, "clip_name": Path(clip_path).name,
                    "raw_duration_s": round(duration_clip, 2),
                    "candidate_count": 0, "rejected_count": 0,
                    "candidate_duration_s": 0, "retention_pct": 0,
                    "rejection_summary": {}, "thumbnail_url": None,
                })
                candidates_by_clip[i] = []
                continue

            candidates, _, summary = build_clip_candidates(windows, duration_clip, global_threshold)

            thumb_url = None
            thumb_t = (
                candidates[0]["start_time"] + min(1.0, candidates[0]["duration"] * 0.25)
                if candidates else duration_clip / 2
            )
            thumb_b64 = await asyncio.to_thread(grab_frame, clip_path, thumb_t)
            if thumb_b64:
                thumb_path = edit_dir / f"thumb_{i}.jpg"
                thumb_path.write_bytes(base64.b64decode(thumb_b64))
                thumb_url = f"/uploads/{job_id}/thumb_{i}.jpg"

            clip_summaries.append({
                "clip_index": i, "clip_name": Path(clip_path).name,
                "thumbnail_url": thumb_url, **summary,
            })
            candidates_by_clip[i] = candidates

        total_raw = round(sum(c["raw_duration_s"] for c in clip_summaries), 2)
        total_cand = round(sum(c["candidate_duration_s"] for c in clip_summaries), 2)
        rough_summary = {
            "clips": clip_summaries,
            "total_clips": len(clip_paths),
            "total_raw_duration_s": total_raw,
            "total_candidate_duration_s": total_cand,
            "overall_retention_pct": round(total_cand / total_raw * 100) if total_raw > 0 else 0,
            "motion_threshold_used": round(global_threshold, 2),
        }

        if all(len(v) == 0 for v in candidates_by_clip.values()):
            _write_state(edit_dir, {
                "status": "error", "job_id": job_id,
                "error": "No usable footage found — all clips were rejected by the rough cut.",
                "rough_cut": rough_summary,
            })
            return

        candidates_store = {
            str(i): [{"clip_path": clip_paths[i], "candidate": c} for c in candidates_by_clip[i]]
            for i in range(len(clip_paths))
        }
        (edit_dir / "candidates.json").write_text(json.dumps(candidates_store))

        _write_state(edit_dir, {
            "status": "awaiting_rough_cut_review",
            "job_id": job_id,
            "rough_cut": rough_summary,
            "_config": {"username": profile.get("username"), "topic": topic, "skip_script": skip_script, "user_id": user_id},
            "_clip_paths": clip_paths,
        })

    except Exception as e:
        _write_state(edit_dir, {"status": "error", "job_id": job_id, "error": str(e)})


# ── Pipeline: Phase 1 (catalog) + Phase 2 (paper edit) ───────────────────────

async def _run_phase1_and_phase2(job_id: str, edit_dir: Path):
    try:
        state = json.loads((edit_dir / "state.json").read_text())
        config = state.get("_config", {})
        clip_paths = state.get("_clip_paths", [])
        rough_cut = state.get("rough_cut", {})

        # Skip Phase 1+2 if already cached (e.g. retrying after a Phase 3 failure)
        catalog_path = edit_dir / "catalog.json"
        manifest_path = edit_dir / "manifest_v2.json"
        if catalog_path.exists() and manifest_path.exists():
            manifest_v2 = json.loads(manifest_path.read_text())
            _write_state(edit_dir, {
                "status": "awaiting_paper_edit_review",
                "job_id": job_id,
                "manifest_v2": manifest_v2,
                "rough_cut": rough_cut,
                "_config": config,
            })
            return

        profile = load_profile_data(config.get("user_id", ""), config.get("username", ""))
        if not profile:
            _write_state(edit_dir, {"status": "error", "job_id": job_id, "error": "Profile not found"})
            return

        candidates_store = json.loads((edit_dir / "candidates.json").read_text())
        candidates_by_clip = {int(k): [item["candidate"] for item in v] for k, v in candidates_store.items()}
        clip_paths_by_idx = {int(k): v[0]["clip_path"] for k, v in candidates_store.items() if v}

        clip_groups = [
            {
                "clip_index": i,
                "clip_path": clip_paths_by_idx.get(i, clip_paths[i] if i < len(clip_paths) else ""),
                "candidates": candidates_by_clip.get(i, []),
            }
            for i in range(len(clip_paths))
            if candidates_by_clip.get(i)
        ]

        if not clip_groups:
            _write_state(edit_dir, {"status": "error", "job_id": job_id, "error": "No usable footage after rough cut."})
            return

        # Phase 1: Catalog all clips in parallel (includes _frame_b64 per scene)
        scenes = await catalog_clips(clip_groups)

        if not scenes:
            _write_state(edit_dir, {"status": "error", "job_id": job_id, "error": "No scenes could be cataloged."})
            return

        # Save thumbnails from Phase 1 frames (no extra ffmpeg calls needed)
        manifest_scenes = []
        for scene in scenes:
            frame_b64 = scene.pop("_frame_b64", None)
            scene.pop("_mid_s", None)           # internal fallback fields, not needed downstream
            scene.pop("_peak_motion_s", None)
            thumb_url = None
            if frame_b64:
                safe_id = scene["scene_id"].replace("/", "_")
                thumb_path = edit_dir / f"scene_{safe_id}.jpg"
                thumb_path.write_bytes(base64.b64decode(frame_b64))
                thumb_url = f"/uploads/{job_id}/scene_{safe_id}.jpg"
            manifest_scenes.append({**scene, "thumbnail_url": thumb_url})

        # Save catalog.json (backend-only — includes clip_path)
        (edit_dir / "catalog.json").write_text(json.dumps({"scenes": scenes}))

        # Save manifest_scenes.json — all scenes with thumbnail URLs (used by replan)
        (edit_dir / "manifest_scenes.json").write_text(json.dumps(manifest_scenes))

        # Phase 2: Paper edit (text-only, no images)
        _write_state(edit_dir, {
            "status": "processing", "job_id": job_id, "step": "planning_edit",
            "rough_cut": rough_cut, "_config": config, "_clip_paths": clip_paths,
        })
        paper_edit = await asyncio.to_thread(plan_edit, scenes, profile)

        # Build manifest_v2 (UI-facing — no clip_path)
        hook_id: str = paper_edit.get("hook_scene_id", "")
        dropped_ids: set[str] = set(paper_edit.get("drop", []))

        # Sort kept scenes by (clip_index, seg_idx) — preserve shooting order
        def _scene_sort_key(s: dict) -> tuple:
            try:
                parts = s["scene_id"].split("_")  # clip_{n}_seg_{m}
                return (int(parts[1]), int(parts[3]))
            except (IndexError, ValueError):
                return (s.get("clip_index", 0), 0)

        kept_scenes = sorted(
            [s for s in manifest_scenes if s["scene_id"] not in dropped_ids],
            key=_scene_sort_key,
        )

        # Duplicate hook to front as a short tease; original stays in chronological body
        hook_scene = next((s for s in kept_scenes if s["scene_id"] == hook_id), None)
        if hook_scene:
            ordered_manifest_scenes = [{**hook_scene, "scene_id": f"{hook_id}_hook", "is_hook": True}] + kept_scenes
        else:
            ordered_manifest_scenes = kept_scenes

        # Strip clip_path from manifest scenes (frontend-safe)
        ui_scenes = [
            {k: v for k, v in s.items() if k != "clip_path"}
            for s in ordered_manifest_scenes
        ]

        dropped_scenes_ui = [
            {k: v for k, v in s.items() if k != "clip_path"}
            for s in manifest_scenes if s["scene_id"] in dropped_ids
        ]

        manifest_v2 = {
            "narrative_summary": paper_edit.get("narrative_summary", ""),
            "reasoning": paper_edit.get("reasoning", ""),
            "hook_scene_id": paper_edit.get("hook_scene_id", ""),
            "scenes": ui_scenes,
            "dropped_scenes": dropped_scenes_ui,
            "dropped_scene_count": len(dropped_ids),
        }

        (edit_dir / "manifest_v2.json").write_text(json.dumps(manifest_v2))
        # Save full paper edit output for debugging / quality review
        (edit_dir / "paper_edit_raw.json").write_text(json.dumps({
            "hook_scene_id": paper_edit.get("hook_scene_id", ""),
            "drop": paper_edit.get("drop", []),
            "reasoning": paper_edit.get("reasoning", ""),
            "duration_hints": paper_edit.get("duration_hints", {}),
        }, indent=2))

        _write_state(edit_dir, {
            "status": "awaiting_paper_edit_review",
            "job_id": job_id,
            "manifest_v2": manifest_v2,
            "rough_cut": rough_cut,
            "_config": config,
        })

    except Exception as e:
        _write_state(edit_dir, {"status": "error", "job_id": job_id, "error": str(e)})


# ── Pipeline: Phase 3 (precision trim) → awaiting_detailed_cut_review ─────────

async def _run_phase3(job_id: str, edit_dir: Path):
    # Keep these in outer scope so the except block can use them for recovery
    config: dict = {}
    rough_cut: dict = {}

    try:
        state = json.loads((edit_dir / "state.json").read_text())
        config = state.get("_config", {})
        approved_ids: list[str] = state.get("_approved_scene_ids", [])
        rough_cut = state.get("rough_cut", {})

        profile = load_profile_data(config.get("user_id", ""), config.get("username", ""))
        if not profile:
            _write_state(edit_dir, {"status": "error", "job_id": job_id, "error": "Profile not found"})
            return

        catalog = json.loads((edit_dir / "catalog.json").read_text())
        scene_map = {s["scene_id"]: s for s in catalog["scenes"]}

        def _resolve_scene(sid: str) -> dict | None:
            if sid in scene_map:
                return scene_map[sid]
            # Hook duplicate: same source clip, trimmed shorter by Phase 3
            if sid.endswith("_hook"):
                base = scene_map.get(sid[:-5])
                if base:
                    return {**base, "scene_id": sid, "is_hook": True}
            return None

        ordered_scenes = [s for sid in approved_ids if (s := _resolve_scene(sid)) is not None]
        if not ordered_scenes:
            _write_state(edit_dir, {"status": "error", "job_id": job_id, "error": "No approved scenes found in catalog."})
            return

        # Merge Phase 2 duration hints into scenes so Phase 3 can use narrative-aware pacing
        duration_hints: dict = {}
        paper_edit_raw_path = edit_dir / "paper_edit_raw.json"
        if paper_edit_raw_path.exists():
            try:
                duration_hints = json.loads(paper_edit_raw_path.read_text()).get("duration_hints", {})
            except Exception:
                pass
        for scene in ordered_scenes:
            sid = scene["scene_id"]
            base_sid = sid[:-5] if sid.endswith("_hook") else sid
            scene["duration_hint"] = duration_hints.get(base_sid, "normal")

        # Use cached Phase 3 output if approved_ids haven't changed
        precision_cuts_path = edit_dir / "precision_cuts.json"
        if precision_cuts_path.exists():
            cached = json.loads(precision_cuts_path.read_text())
            if cached.get("approved_ids") == approved_ids:
                precision_cuts = cached["cuts"]
            else:
                precision_cuts = await asyncio.to_thread(trim_scenes, ordered_scenes, profile)
        else:
            precision_cuts = await asyncio.to_thread(trim_scenes, ordered_scenes, profile)

        # Save Phase 3 output — includes Claude's note + confidence per cut
        precision_cuts_path.write_text(json.dumps({
            "approved_ids": approved_ids,
            "cuts": precision_cuts,
        }, indent=2))

        # Extract per-cut thumbnails and build ui_cuts
        ui_cuts = []
        detailed_cuts = []
        for i, cut in enumerate(precision_cuts):
            thumb_b64 = await asyncio.to_thread(grab_frame, cut["clip_path"], cut["start_s"])
            thumb_url = None
            if thumb_b64:
                thumb_path = edit_dir / f"cut_thumb_{i}.jpg"
                thumb_path.write_bytes(base64.b64decode(thumb_b64))
                thumb_url = f"/uploads/{job_id}/cut_thumb_{i}.jpg"

            scene = scene_map.get(cut["scene_id"], {})
            ui_cuts.append({
                "cut_index": i,
                "scene_id": cut["scene_id"],
                "clip_index": cut["clip_index"],
                "start_s": cut["start_s"],
                "end_s": cut["end_s"],
                "duration_s": cut["duration_s"],
                "note": cut["note"],
                "confidence": cut["confidence"],
                "thumbnail_url": thumb_url,
                "description": scene.get("description", ""),
            })
            detailed_cuts.append({**cut, "cut_index": i})

        _write_state(edit_dir, {
            "status": "awaiting_detailed_cut_review",
            "job_id": job_id,
            "ui_cuts": ui_cuts,
            "detailed_cuts": detailed_cuts,
            "rough_cut": rough_cut,
            "_config": config,
        })

    except Exception as e:
        # Phase 3 failed — recover to paper_edit_review using cached manifest_v2.json
        # so the user can retry without re-running the expensive Phase 1+2 catalog calls.
        manifest_v2_path = edit_dir / "manifest_v2.json"
        if manifest_v2_path.exists():
            try:
                manifest_v2 = json.loads(manifest_v2_path.read_text())
                _write_state(edit_dir, {
                    "status": "awaiting_paper_edit_review",
                    "job_id": job_id,
                    "manifest_v2": manifest_v2,
                    "rough_cut": rough_cut,
                    "_config": config,
                    "phase3_error": str(e),
                })
                return
            except Exception:
                pass
        # Fallback: hard error if manifest_v2.json is also unreadable
        _write_state(edit_dir, {"status": "error", "job_id": job_id, "error": str(e)})


# ── Pipeline: render (after user approves detailed cuts) ──────────────────────

async def _render_edit(
    job_id: str,
    edit_dir: Path,
    profile: dict,
    detailed_cuts: list[dict],
    drop: list[int],
    topic: str,
    skip_script: bool,
):
    try:
        segments = [
            {"clip_path": cut["clip_path"], "start_s": cut["start_s"], "end_s": cut["end_s"]}
            for i, cut in enumerate(detailed_cuts)
            if i not in drop
        ]

        if not segments:
            _write_state(edit_dir, {"status": "error", "job_id": job_id, "error": "No segments after applying drops."})
            return

        _write_state(edit_dir, {"status": "processing", "job_id": job_id, "step": "building_selects"})
        selects_path = await asyncio.to_thread(_build_selects_from_cuts, segments, edit_dir)

        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(selects_path)],
            capture_output=True, text=True,
        )
        duration = 30.0
        if probe.returncode == 0:
            duration = float(json.loads(probe.stdout).get("format", {}).get("duration", 30))

        script = None
        caption_plan = None
        if not skip_script:
            _write_state(edit_dir, {"status": "processing", "job_id": job_id, "step": "generating_script"})
            catalog_cuts = _build_catalog_cuts(detailed_cuts, drop, edit_dir)
            script = await asyncio.to_thread(
                generate_script_and_captions, profile, catalog_cuts, duration, topic
            )
            caption_plan = script.get("caption_plan") if isinstance(script, dict) else None

        _write_state(edit_dir, {"status": "processing", "job_id": job_id, "step": "rendering"})

        # Rename selects.mp4 to a UUID-named output file
        import uuid as _uuid
        mp4_path = edit_dir / f"edit_{_uuid.uuid4()}.mp4"
        selects_path.rename(mp4_path)

        # Probe real output duration
        probe_dur = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4_path)],
            capture_output=True, text=True,
        )
        output_duration = round(float(probe_dur.stdout.strip()), 1) if probe_dur.returncode == 0 and probe_dur.stdout.strip() else 0.0

        edit_result = {
            "mp4_path": str(mp4_path),
            "mp4_filename": mp4_path.name,
            "cuts_applied": len(segments),
            "output_duration_s": output_duration,
            "file_size_bytes": mp4_path.stat().st_size if mp4_path.exists() else 0,
        }

        # FCPXML — references original source clips with per-cut in/out timecodes
        # so the creator can revert, extend, or trim any cut in Final Cut Pro.
        fcpxml_stem = mp4_path.stem
        fcpxml_path = edit_dir / f"{fcpxml_stem}.fcpxml"
        active_cuts = [cut for i, cut in enumerate(detailed_cuts) if i not in drop]
        await asyncio.to_thread(
            generate_fcpxml,
            active_cuts,
            str(fcpxml_path),
            f"auto-edit-{profile.get('username', 'edit')}",
            caption_plan,
        )

        # SRT — editable captions for CapCut / Final Cut / Premiere
        srt_path = None
        if caption_plan:
            srt_path = edit_dir / f"{fcpxml_stem}.srt"
            srt_path.write_text(_build_srt(caption_plan))

        # Build project ZIP (FCPXML + source clips) for DaVinci/FCP import with one-click relink
        zip_path = edit_dir / f"{fcpxml_stem}_project.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
            zf.write(fcpxml_path, fcpxml_path.name)
            seen_clips: set[str] = set()
            for cut in active_cuts:
                cp = cut.get("clip_path", "")
                if cp and cp not in seen_clips and Path(cp).exists():
                    zf.write(cp, Path(cp).name)
                    seen_clips.add(cp)

        # Upload final outputs to Supabase Storage (no-op if not configured)
        mp4_url = await asyncio.to_thread(upload_output, Path(edit_result["mp4_path"]), job_id)
        fcpxml_url = await asyncio.to_thread(upload_output, fcpxml_path, job_id)
        zip_url = await asyncio.to_thread(upload_output, zip_path, job_id)
        srt_url = await asyncio.to_thread(upload_output, srt_path, job_id) if srt_path else None

        _write_state(edit_dir, {
            "status": "completed",
            "job_id": job_id,
            "result": {
                **edit_result,
                "mp4_url": mp4_url,
                "fcpxml_path": str(fcpxml_path),
                "fcpxml_url": fcpxml_url,
                "fcpxml_filename": fcpxml_path.name,
                "zip_url": zip_url,
                "zip_filename": zip_path.name,
                "srt_path": str(srt_path) if srt_path else None,
                "srt_url": srt_url,
                "srt_filename": srt_path.name if srt_path else None,
                "script": script,
            },
        })

    except Exception as e:
        _write_state(edit_dir, {"status": "error", "job_id": job_id, "error": str(e)})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_srt(caption_plan: list[dict]) -> str:
    def _ts(s: float) -> str:
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(sec):02d},{int((s % 1) * 1000):03d}"
    blocks = []
    for i, cap in enumerate(caption_plan, 1):
        start = cap.get("timestamp_s", 0.0)
        end = start + cap.get("duration_s", 2.0)
        blocks.append(f"{i}\n{_ts(start)} --> {_ts(end)}\n{cap.get('text', '')}")
    return "\n\n".join(blocks) + "\n"


def _build_catalog_cuts(detailed_cuts: list[dict], drop: list[int], edit_dir: Path) -> list[dict]:
    """
    Merge Phase 3 cut timing with Phase 1 catalog metadata and compute each cut's
    absolute position in the final edit. Passed to the scriptwriter so it can
    write narration that references actual visual content beat-by-beat.
    """
    try:
        catalog = json.loads((edit_dir / "catalog.json").read_text())
        scene_map = {s["scene_id"]: s for s in catalog.get("scenes", [])}
    except Exception:
        scene_map = {}

    result = []
    edit_position = 0.0
    for i, cut in enumerate(detailed_cuts):
        if i in drop:
            continue
        dur = cut.get("duration_s", cut.get("end_s", 0) - cut.get("start_s", 0))
        catalog_entry = scene_map.get(cut.get("scene_id", ""), {})
        result.append({
            "edit_start_s": round(edit_position, 3),
            "edit_end_s": round(edit_position + dur, 3),
            "duration_s": round(dur, 3),
            "intent": catalog_entry.get("intent", "process"),
            "subject": catalog_entry.get("subject", ""),
            "description": catalog_entry.get("description", ""),
            "start_state": catalog_entry.get("start_state", ""),
            "end_state": catalog_entry.get("end_state", ""),
            "shot_type": catalog_entry.get("shot_type", ""),
            "energy": catalog_entry.get("energy", ""),
        })
        edit_position += dur
    return result


def _build_selects_from_cuts(segments: list[dict], output_dir: Path) -> Path:
    # Probe each unique source clip once so we can clamp end_s to the actual duration.
    # If end_s overshoots (Phase 3 rounding or ffprobe imprecision), ffmpeg encodes
    # to the end of the stream then pads video with a frozen last frame while audio
    # continues — visible as a freeze at the end of the last cut in that clip.
    clip_durations: dict[str, float] = {}
    for seg in segments:
        cp = seg["clip_path"]
        if cp not in clip_durations:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", cp],
                capture_output=True, text=True,
            )
            if probe.returncode == 0:
                clip_durations[cp] = float(
                    json.loads(probe.stdout).get("format", {}).get("duration", 9999.0)
                )
            else:
                clip_durations[cp] = 9999.0

    segment_paths = []
    for i, seg in enumerate(segments):
        seg_out = output_dir / f"select_{i:03d}.mp4"
        clip_dur = clip_durations.get(seg["clip_path"], 9999.0)
        end_s = min(seg["end_s"], clip_dur)
        start_s = seg["start_s"]
        dur = max(0.1, end_s - start_s)
        # Fast input seek (-ss before -i), force 30fps constant frame rate (-r 30),
        # and resample audio to match video timeline (-af aresample=async=1).
        # This normalizes VFR iPhone video and eliminates frozen last frames.
        cmd = [
            "ffmpeg",
            "-ss", f"{start_s:.3f}", "-i", seg["clip_path"],
            "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
            "-r", "30",
            "-c:a", "aac", "-b:a", "192k",
            "-af", "aresample=async=1",
            str(seg_out), "-y",
        ]
        subprocess.run(cmd, capture_output=True, text=True)
        if seg_out.exists() and seg_out.stat().st_size > 0:
            segment_paths.append(seg_out)

    if not segment_paths:
        raise RuntimeError("No segments could be extracted from detailed cuts")
    if len(segment_paths) == 1:
        return segment_paths[0]
    return _concat_clips(segment_paths, output_dir, out_name="selects.mp4")


def _remux_to_mp4(src: Path, job_dir: Path, index: int = 0) -> Path:
    out = job_dir / f"clip_{index:02d}.mp4"
    cmd = ["ffmpeg", "-fflags", "+genpts", "-i", str(src), "-c", "copy", str(out), "-y"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        cmd = [
            "ffmpeg", "-i", str(src),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k", str(out), "-y",
        ]
        subprocess.run(cmd, capture_output=True, text=True)
    return out


def _concat_clips(clips: list[Path], job_dir: Path, out_name: str = "footage.mp4") -> Path:
    # Concat demuxer with stream copy — segments are already normalized to constant
    # 30fps with synced A/V, so re-encoding is unnecessary and slow.
    # -fflags +genpts regenerates presentation timestamps on read for clean joins.
    out_path = job_dir / out_name
    list_path = job_dir / "concat_list.txt"
    list_path.write_text("\n".join(f"file '{Path(c).absolute()}'" for c in clips))
    cmd = [
        "ffmpeg",
        "-fflags", "+genpts",
        "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-c", "copy",
        str(out_path), "-y",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"Concat failed: {result.stderr[-400:]}")
    return out_path


def _download_file(job_id: str, path_key: str, media_type: str, filename: str):
    state = _get_completed_state(job_id)
    result = state.get("result", {})

    # Redirect to Supabase public URL if available (production)
    url_key = path_key.replace("_path", "_url")
    public_url = result.get(url_key)
    if public_url:
        download_url = public_url if "?" in public_url else f"{public_url}?download={filename}"
        return RedirectResponse(download_url)

    # Fall back to local file (dev, no Supabase configured)
    file_path = result.get(path_key)
    if not file_path or not Path(file_path).exists():
        raise HTTPException(404, "File not found")
    return FileResponse(file_path, media_type=media_type, filename=filename)


def _get_completed_state(job_id: str) -> dict:
    state_path = UPLOAD_DIR / job_id / "state.json"
    if not state_path.exists():
        raise HTTPException(404, "Job not found")
    state = json.loads(state_path.read_text())
    if state.get("status") != "completed":
        raise HTTPException(400, f"Edit not complete (status: {state.get('status')})")
    return state


def _write_state(job_dir: Path, state: dict):
    (job_dir / "state.json").write_text(json.dumps(state))
