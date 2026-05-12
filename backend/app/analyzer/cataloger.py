"""
Phase 1: Scene Catalog.

For each clip, describes every candidate segment using Claude Vision (Haiku).
All clips are processed in parallel via asyncio.gather.

Results are cached globally by clip file fingerprint + candidate timestamps.
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
  description    — one-sentence visual description
  _frame_b64     — midpoint frame (caller saves as thumbnail then discards)
"""
import re
import json
import asyncio
import anthropic
import os

from app.analyzer.frames import grab_frame
from app.analyzer.cache import get_clip_cache_key, load_phase1_cache, save_phase1_cache

_MODEL = "claude-haiku-4-5-20251001"  # cheap, fast, sufficient for descriptions


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

    # Step 1: Build seg_metas and grab frames (always needed for thumbnails,
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
            "_frame_b64": frame,
        })

    if not seg_metas:
        return []

    # Step 2: Check global Phase 1 cache
    cache_key = get_clip_cache_key(clip_path, candidates)
    cached = load_phase1_cache(cache_key)
    if cached:
        desc_map = {d["scene_id"]: d for d in cached}
        return [
            {
                **meta,
                "shot_type": desc_map.get(meta["scene_id"], {}).get("shot_type", "unknown"),
                "energy": desc_map.get(meta["scene_id"], {}).get("energy", "medium"),
                "description": desc_map.get(meta["scene_id"], {}).get("description", ""),
            }
            for meta in seg_metas
        ]

    # Step 3: Cache miss — call Claude Vision with 3 frames per segment
    # (25%, 50%, 75%) so Claude can see action arc, not just a static midpoint.
    # The 50% frame reuses _frame_b64 (already grabbed) to save one ffmpeg call.
    content = []
    for meta in seg_metas:
        s, e, dur = meta["start_s"], meta["end_s"], meta["duration_s"]
        content.append({"type": "text", "text": f"[{meta['scene_id']} — {dur:.1f}s]"})
        for t, label in [
            (s + dur * 0.25, "start"),
            (s + dur * 0.50, "mid"),
            (s + dur * 0.75, "end"),
        ]:
            frame = meta["_frame_b64"] if label == "mid" else grab_frame(clip_path, t)
            if frame:
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": frame},
                })

    content.append({
        "type": "text",
        "text": (
            "For each segment labeled above, give a one-sentence visual description.\n"
            "Return ONLY valid JSON:\n"
            '{"segments": ['
            '{"scene_id": "<id>", "shot_type": "close-up|medium|wide|unknown", '
            '"energy": "high|medium|low", "description": "<one sentence>"}'
            "]}"
        ),
    })

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
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
    scenes = []
    for meta in seg_metas:
        desc = desc_map.get(meta["scene_id"], {})
        scenes.append({
            **meta,
            "shot_type": desc.get("shot_type", "unknown"),
            "energy": desc.get("energy", "medium"),
            "description": desc.get("description", ""),
        })

    # Step 4: Persist descriptions to global cache (frames excluded — job-specific)
    save_phase1_cache(cache_key, [
        {
            "scene_id": s["scene_id"],
            "shot_type": s["shot_type"],
            "energy": s["energy"],
            "description": s["description"],
        }
        for s in scenes
    ])

    return scenes


def _minimal_entries(seg_metas: list[dict]) -> list[dict]:
    return [{**m, "shot_type": "unknown", "energy": "medium", "description": ""} for m in seg_metas]
