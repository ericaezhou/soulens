"""
Phase 1: Scene Catalog.

For each clip, describes every candidate segment using Claude Sonnet Vision.
All clips are processed in parallel via asyncio.gather.

Results are cached globally by clip file fingerprint + candidate timestamps + schema version.
Re-uploading the same footage skips Claude entirely for Phase 1.

Each SceneEntry returned:
  scene_id       — "clip_{clip_index}_seg_{seg_index}" (deterministic, filename-safe)
  clip_index     — source clip number
  clip_path      — absolute path (backend-only, stripped before manifest_v2)
  start_s        — segment start within clip file
  end_s          — segment end within clip file
  duration_s     — segment duration
  shot_type      — "close-up" | "medium" | "wide" | "unknown"
  energy         — "high" | "medium" | "low"
  intent         — "establishment" | "process" | "payoff" | "transition"
  subject        — short phrase of what's in frame (e.g. "hands kneading dough")
  description    — one-sentence arc of the whole segment
  start_state    — brief phrase: what's happening at the very start of the segment
  end_state      — brief phrase: what's happening at the very end of the segment
  action_complete — True if the action shown reaches a natural conclusion in frame
  key_moment_s   — absolute clip timestamp of the single most visually striking frame
  face_visible   — True if a human face is visible
  camera_motion  — "static" | "pan" | "tilt" | "zoom" | "handheld"
  _frame_b64     — midpoint frame (caller saves as thumbnail then discards)
"""
import re
import json
import asyncio
import anthropic
import os

from app.analyzer.frames import grab_frame
from app.analyzer.cache import get_clip_cache_key, load_phase1_cache, save_phase1_cache

_MODEL = "claude-sonnet-4-6"

# 4 frame positions as fractions of segment duration.
# Start (5%) anchors start_state. End (88%) anchors end_state — stopping at 88% rather than
# 95% avoids "dead frames" where the creator has stopped but not yet hit the record button
# (camera lowering, accidental trailing footage, etc.).
_FRAME_POSITIONS = [0.05, 0.33, 0.67, 0.88]

# All fields Claude returns — used for cache serialization and fallback defaults.
_CLAUDE_FIELDS = [
    "shot_type", "energy", "intent", "subject", "description",
    "start_state", "end_state", "action_complete", "key_moment_s",
    "face_visible", "camera_motion",
]

_FALLBACK_DEFAULTS = {
    "shot_type": "unknown",
    "energy": "medium",
    "intent": "process",
    "subject": "",
    "description": "",
    "start_state": "",
    "end_state": "",
    "action_complete": True,
    "key_moment_s": None,   # caller fills in midpoint if None
    "face_visible": False,
    "camera_motion": "static",
}


async def catalog_clips(clip_groups: list[dict]) -> list[dict]:
    """Describe all candidate segments across clips in parallel. Returns flat SceneEntry list."""
    results = await asyncio.gather(*[
        asyncio.to_thread(_catalog_one_clip, group)
        for group in clip_groups
    ])
    return [scene for clip_scenes in results for scene in clip_scenes]


def _catalog_one_clip(group: dict) -> list[dict]:
    clip_index = group["clip_index"]
    clip_path = group["clip_path"]
    candidates = group["candidates"]

    if not candidates:
        return []

    # Step 1: Build seg_metas and grab midpoint frame (always needed for thumbnails,
    # regardless of cache hit). Frame grabbing is fast and free.
    seg_metas: list[dict] = []
    for seg_idx, cand in enumerate(candidates):
        start_s = float(cand["start_time"])
        end_s = float(cand["end_time"])
        dur = end_s - start_s
        if dur < 0.1:
            continue

        mid = (start_s + end_s) / 2
        frame = grab_frame(clip_path, mid)
        if not frame:
            continue

        seg_metas.append({
            "scene_id": f"clip_{clip_index}_seg_{seg_idx}",
            "clip_index": clip_index,
            "clip_path": clip_path,
            "start_s": round(start_s, 3),
            "end_s": round(end_s, 3),
            "duration_s": round(dur, 3),
            "_frame_b64": frame,                          # midpoint frame → thumbnail
            "_mid_s": round(mid, 3),                      # midpoint fallback
            "_peak_motion_s": cand.get("peak_motion_s"),  # optical flow peak from rough cut
        })

    if not seg_metas:
        return []

    # Step 2: Check global Phase 1 cache
    cache_key = get_clip_cache_key(clip_path, candidates)
    cached = load_phase1_cache(cache_key)
    if cached:
        desc_map = {d["scene_id"]: d for d in cached}
        return [_merge_meta_with_cache(meta, desc_map.get(meta["scene_id"], {})) for meta in seg_metas]

    # Step 3: Cache miss — call Claude Sonnet Vision with 4 frames per segment.
    # Positions: 5% (start state), 33%, 67%, 95% (end state) — captures the full action arc.
    content = []
    for meta in seg_metas:
        s, e, dur = meta["start_s"], meta["end_s"], meta["duration_s"]
        peak = meta.get("_peak_motion_s")
        peak_note = f" | optical flow peak @ {peak:.2f}s" if peak is not None else ""
        content.append({"type": "text", "text": f"\n[{meta['scene_id']} — {dur:.1f}s{peak_note}]"})
        for frac in _FRAME_POSITIONS:
            t = round(s + dur * frac, 3)
            frame = grab_frame(clip_path, t)
            if frame:
                content.append({"type": "text", "text": f"  frame @ {t:.2f}s"})
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": frame},
                })

    content.append({
        "type": "text",
        "text": (
            "You are analyzing video segments for an Instagram Reel editor.\n"
            "For each labeled segment you received 4 frames: start (~5%), early (~33%), "
            "late (~67%), and end (~88%). Use all 4 together to understand the full arc.\n"
            "Treat each segment as a standalone unit. Do not assume the subject of Segment B"
            "is the same as Segment A unless you see it in the provided frames.\n"
            "Be concise: description ≤ 10 words, subject/start_state/end_state ≤ 6 words each.\n\n"
            "Return ONLY valid JSON:\n"
            '{"segments": [{\n'
            '  "scene_id": "<id>",\n'
            '  "shot_type": "close-up|medium|wide|unknown",\n'
            '  "energy": "high|medium|low",\n'
            '  "intent": "establishment|process|payoff|transition",\n'
            '  "subject": "<what is in frame — one short phrase, e.g. \'hands kneading dough\'>",\n'
            '  "description": "<one sentence describing what happens across the whole segment>",\n'
            '  "start_state": "<brief phrase: what is happening at the very start>",\n'
            '  "end_state": "<brief phrase: what is happening at the very end>",\n'
            '  "action_complete": <true if the action shown reaches a natural conclusion in frame, false if it cuts off mid-action>,\n'
            '  "key_moment_s": <float — use the frame timestamps shown above; pick the single most visually striking moment; interpolate between frames if needed>,\n'
            '  "face_visible": <true|false>,\n'
            '  "camera_motion": "static|pan|tilt|zoom|handheld"\n'
            "}]}\n\n"
            "Field guidance:\n"
            "  intent — establishment: sets context/ingredients/location/plating surface; "
            "process: action in progress (chopping, pouring, cooking, mixing); "
            "payoff: satisfying result or completion (plated dish, final reveal, reaction shot); "
            "transition: neutral connecting shot with no strong content beat\n"
            "  energy — high: fast motion or dramatic reveal; medium: active but controlled; low: slow or static\n"
            "  action_complete — false if the action clearly continues beyond the clip end\n"
            "  key_moment_s — the timestamp (from the frame labels) of the single best frame; "
            "interpolate to a value between two frame timestamps if the peak falls between them\n"
            "  camera_motion — static: no movement; handheld: slight organic drift; "
            "pan/tilt: deliberate horizontal/vertical camera move; zoom: focal length change"
        ),
    })

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": content}],
        )
        text = response.content[0].text.strip()
    except Exception:
        return _minimal_entries(seg_metas)

    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return _minimal_entries(seg_metas)

    json_str = match.group()
    try:
        result = json.loads(json_str)
    except json.JSONDecodeError:
        json_str = re.sub(r"[\x00-\x1f\x7f]", " ", json_str)
        try:
            result = json.loads(json_str)
        except json.JSONDecodeError:
            return _minimal_entries(seg_metas)

    desc_map = {s["scene_id"]: s for s in result.get("segments", [])}
    scenes = [_merge_meta_with_claude(meta, desc_map.get(meta["scene_id"], {})) for meta in seg_metas]

    # Step 4: Persist to global cache (frames excluded — job-specific)
    save_phase1_cache(cache_key, [
        {field: s[field] for field in _CLAUDE_FIELDS if field in s} | {"scene_id": s["scene_id"]}
        for s in scenes
    ])

    return scenes


# ── Internal ──────────────────────────────────────────────────────────────────

def _merge_meta_with_claude(meta: dict, raw: dict) -> dict:
    """Merge seg_meta with Claude's parsed output, applying field-level defaults."""
    return {
        **meta,
        "shot_type": raw.get("shot_type", _FALLBACK_DEFAULTS["shot_type"]),
        "energy": raw.get("energy", _FALLBACK_DEFAULTS["energy"]),
        "intent": raw.get("intent", _FALLBACK_DEFAULTS["intent"]),
        "subject": raw.get("subject", ""),
        "description": raw.get("description", ""),
        "start_state": raw.get("start_state", ""),
        "end_state": raw.get("end_state", ""),
        "action_complete": bool(raw.get("action_complete", True)),
        "key_moment_s": _coerce_key_moment(
            raw.get("key_moment_s"), meta["start_s"], meta["end_s"],
            meta.get("_peak_motion_s"), meta["_mid_s"],
        ),
        "face_visible": bool(raw.get("face_visible", False)),
        "camera_motion": raw.get("camera_motion", _FALLBACK_DEFAULTS["camera_motion"]),
    }


def _merge_meta_with_cache(meta: dict, cached: dict) -> dict:
    """Merge seg_meta with a cache hit, applying field-level defaults for any missing fields
    (handles partial cache entries if schema was extended mid-session)."""
    return {
        **meta,
        "shot_type": cached.get("shot_type", _FALLBACK_DEFAULTS["shot_type"]),
        "energy": cached.get("energy", _FALLBACK_DEFAULTS["energy"]),
        "intent": cached.get("intent", _FALLBACK_DEFAULTS["intent"]),
        "subject": cached.get("subject", ""),
        "description": cached.get("description", ""),
        "start_state": cached.get("start_state", ""),
        "end_state": cached.get("end_state", ""),
        "action_complete": bool(cached.get("action_complete", True)),
        "key_moment_s": _coerce_key_moment(
            cached.get("key_moment_s"), meta["start_s"], meta["end_s"],
            meta.get("_peak_motion_s"), meta["_mid_s"],
        ),
        "face_visible": bool(cached.get("face_visible", False)),
        "camera_motion": cached.get("camera_motion", _FALLBACK_DEFAULTS["camera_motion"]),
    }


def _coerce_key_moment(
    val, start_s: float, end_s: float, peak_motion_s: float | None, mid_s: float
) -> float:
    """Clamp key_moment_s to source bounds. Fallback chain: Claude → optical flow peak → midpoint."""
    try:
        t = float(val)
        return round(max(start_s, min(t, end_s)), 3)
    except (TypeError, ValueError):
        fallback = peak_motion_s if peak_motion_s is not None else mid_s
        return round(max(start_s, min(fallback, end_s)), 3)


def _minimal_entries(seg_metas: list[dict]) -> list[dict]:
    """Fallback when Claude call or JSON parse fails — fill all fields with safe defaults."""
    return [
        {
            **m,
            **_FALLBACK_DEFAULTS,
            "key_moment_s": _coerce_key_moment(
                None, m["start_s"], m["end_s"], m.get("_peak_motion_s"), m["_mid_s"]
            ),
        }
        for m in seg_metas
    ]
