"""
Phase 3: Precision Trim — sliding window.

Processes scenes in blocks of BLOCK_SIZE. Each block receives:
  - 1 context scene (last cut from the previous block, for continuity)
  - BLOCK_SIZE new scenes to trim, with 4 frames each

Claude returns exact start_s / end_s per scene plus a confidence score.
Low-confidence cuts fall back to a center-cut at target_cut_s length.

Phase 1 metadata used as soft anchors:
  - key_moment_s: Claude should try to include this timestamp, but continuity takes priority
  - action_complete: if False, prefer ending before the action cuts off rather than after
  - start_state / end_state: context about what's happening at segment boundaries

PrecisionCut schema returned per scene:
  scene_id, clip_index, clip_path, start_s, end_s, duration_s, note, confidence
"""
import re
import json

from app.analyzer.frames import grab_frame
from app.llm import get_client, claude_model
BLOCK_SIZE = 3
CONFIDENCE_THRESHOLD = 0.6
MIN_CUT_S = 1.5
MAX_CUT_S = 6.0
HOOK_MAX_CUT_S = 2.0  # hook tease is always short — highest energy moment only
FRAMES_PER_SCENE = 4

# Phase 2 assigns a narrative timing category per scene; Phase 3 resolves it
# to a target duration by multiplying the creator's avg cut (target_cut_s).
HINT_MULTIPLIERS = {
    "fast":    0.7,   # B-roll, transitions, already-understood action
    "normal":  1.0,   # creator's baseline heartbeat
    "breathe": 1.6,   # cultural context, wide reveals — let it land
    "long":    2.2,   # money shot / emotional payoff — one or two per edit
}


def trim_scenes(ordered_scenes: list[dict], profile: dict) -> list[dict]:
    """
    Sliding window precision trim. Returns flat list of PrecisionCut dicts
    in the same order as ordered_scenes.
    """
    if not ordered_scenes:
        return []

    recipe = profile.get("edit_recipe", {})
    synthesis = profile.get("synthesis", {})
    target_cut_s = (
        recipe.get("target_cut_duration")
        or synthesis.get("pacing_pattern", {}).get("target_avg_cut_s")
        or 2.5
    )

    cuts: list[dict] = []
    context_cut: dict | None = None

    for block_start in range(0, len(ordered_scenes), BLOCK_SIZE):
        block = ordered_scenes[block_start : block_start + BLOCK_SIZE]
        block_cuts = _trim_block(block, context_cut, profile, target_cut_s)
        cuts.extend(block_cuts)
        if block_cuts:
            context_cut = block_cuts[-1]

    return cuts


# ── Internal ──────────────────────────────────────────────────────────────────

def _trim_block(
    scenes: list[dict],
    context_cut: dict | None,
    profile: dict,
    target_cut_s: float,
) -> list[dict]:
    username = profile.get("username", "this creator")
    synthesis = profile.get("synthesis", {})
    hook_formula = synthesis.get("hook_formula", "")
    money_shot = synthesis.get("cooking_narrative", {}).get("money_shot", "")

    content = []

    if context_cut:
        content.append({
            "type": "text",
            "text": (
                "PREVIOUS CUT (context only — do NOT re-cut this):\n"
                f"  Scene {context_cut['scene_id']} · "
                f"{context_cut['start_s']:.2f}s → {context_cut['end_s']:.2f}s "
                f"({context_cut['duration_s']:.1f}s) — {context_cut['note']}\n"
                "Your first cut must flow naturally from this.\n"
            ),
        })

    for scene in scenes:
        dur = scene["duration_s"]
        n_frames = min(FRAMES_PER_SCENE, max(2, round(dur / 1.5)))
        hook_note = " [HOOK TEASE — max 2s, pick the single most striking moment]" if scene.get("is_hook") else ""
        key_moment = scene.get("key_moment_s")
        start_state = scene.get("start_state", "")
        end_state = scene.get("end_state", "")
        action_complete = scene.get("action_complete", True)

        hint = scene.get("duration_hint", "normal")
        scene_target_s = target_cut_s * HINT_MULTIPLIERS.get(hint, 1.0)
        # Hook always overrides to short tease regardless of narrative hint
        if scene.get("is_hook"):
            scene_target_s = HOOK_MAX_CUT_S

        meta_lines = [
            f"Description: {scene['description']}",
            f"Target: {scene_target_s:.1f}s ({hint})",
        ]
        if key_moment is not None:
            meta_lines.append(
                f"Peak moment: {key_moment:.2f}s — include this if it flows naturally. "
                f"If including it would cause a mid-blink, mid-shake, or jarring cut, "
                f"exclude it and use the highest-energy frames available instead."
            )
        if start_state:
            meta_lines.append(f"Starts: {start_state}")
        if end_state:
            meta_lines.append(f"Ends: {end_state}")
        if not action_complete:
            meta_lines.append("Action incomplete: ends mid-action — prefer cutting before the action trails off rather than keeping the abrupt end")

        content.append({
            "type": "text",
            "text": (
                f"\n[{scene['scene_id']}] {scene['shot_type']} · {dur:.1f}s "
                f"(source: {scene['start_s']:.2f}s → {scene['end_s']:.2f}s){hook_note}\n"
                + "\n".join(meta_lines)
            ),
        })

        for frame_b64, label in _sample_frames(scene, n_frames):
            content.append({"type": "text", "text": label})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": frame_b64},
            })

    scene_ids = [s["scene_id"] for s in scenes]
    content.append({
        "type": "text",
        "text": (
            f"You are precision-trimming cuts for @{username}.\n"
            + (f"Hook formula: {hook_formula}\n" if hook_formula else "")
            + (f"Money shot: {money_shot}\n" if money_shot else "")
            + f"\nFor each scene ({', '.join(scene_ids)}), pick the exact in-point and out-point.\n"
            f"Rules:\n"
            f"  - start_s / end_s must be within the scene's source range shown above\n"
            f"  - Minimum {MIN_CUT_S}s per cut; respect each scene's 'Target' duration — it reflects the narrative beat\n"
            f"  - Scenes marked [HOOK TEASE]: trim to max {HOOK_MAX_CUT_S}s — find the single peak moment\n"
            f"  - If a 'Peak moment' timestamp is given, include it if continuity allows — prioritize smooth, watchable cuts over forcing a specific frame\n"
            f"  - Start after motion begins; end at a visual peak or completed action\n"
            f"  - confidence: 0.0–1.0 (lower if frames are blurry or action unclear)\n\n"
            "Return ONLY valid JSON:\n"
            '{"cuts": ['
            '{"scene_id": "<id>", "start_s": <float>, "end_s": <float>, '
            '"confidence": <0.0-1.0>, "note": "<what moment>"}'
            "]}"
        ),
    })

    client = get_client()

    try:
        response = client.messages.create(
            model=claude_model(),
            max_tokens=1024,
            messages=[{"role": "user", "content": content}],
        )
        text = response.content[0].text.strip()
    except Exception:
        return [_fallback(s, target_cut_s, "API call failed") for s in scenes]

    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return [_fallback(s, target_cut_s, "no JSON returned") for s in scenes]

    json_str = match.group()
    try:
        result = json.loads(json_str)
    except json.JSONDecodeError:
        json_str = re.sub(r"[\x00-\x1f\x7f]", " ", json_str)
        try:
            result = json.loads(json_str)
        except json.JSONDecodeError:
            return [_fallback(s, target_cut_s, "JSON parse failed") for s in scenes]

    scene_map = {s["scene_id"]: s for s in scenes}
    cuts: list[dict] = []

    for raw in result.get("cuts", []):
        sid = raw.get("scene_id", "")
        scene = scene_map.get(sid)
        if not scene:
            continue

        start_s = float(raw.get("start_s", scene["start_s"]))
        end_s = float(raw.get("end_s", scene["end_s"]))
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.5))))
        note = raw.get("note", "")

        # Clamp to source bounds using per-scene narrative target
        hint = scene.get("duration_hint", "normal")
        scene_target_s = target_cut_s * HINT_MULTIPLIERS.get(hint, 1.0)
        if scene.get("is_hook"):
            effective_max = HOOK_MAX_CUT_S
        else:
            effective_max = min(MAX_CUT_S, scene_target_s * 1.5, scene["end_s"] - scene["start_s"])
        start_s = max(scene["start_s"], min(start_s, scene["end_s"] - MIN_CUT_S))
        end_s = max(start_s + MIN_CUT_S, min(end_s, start_s + effective_max, scene["end_s"]))
        dur = end_s - start_s

        if confidence < CONFIDENCE_THRESHOLD or dur < MIN_CUT_S:
            cut = _fallback(scene, target_cut_s, f"{note} [fallback: confidence={confidence:.2f}]")
        else:
            cut = {
                "scene_id": sid,
                "clip_index": scene["clip_index"],
                "clip_path": scene["clip_path"],
                "start_s": round(start_s, 3),
                "end_s": round(end_s, 3),
                "duration_s": round(dur, 3),
                "note": note,
                "confidence": round(confidence, 2),
            }
        cuts.append(cut)

    # Fallback for scenes Claude skipped
    returned = {c["scene_id"] for c in cuts}
    for scene in scenes:
        if scene["scene_id"] not in returned:
            cuts.append(_fallback(scene, target_cut_s, "not returned by Claude"))

    # Restore input order
    idx_map = {s["scene_id"]: i for i, s in enumerate(scenes)}
    cuts.sort(key=lambda c: idx_map.get(c["scene_id"], 999))

    return cuts


def _sample_frames(scene: dict, n: int) -> list[tuple[str, str]]:
    start, end = scene["start_s"], scene["end_s"]
    dur = end - start
    times = [start + dur * i / (n - 1) for i in range(n)] if n > 1 else [start + dur / 2]
    result = []
    for t in times:
        frame = grab_frame(scene["clip_path"], t)
        if frame:
            result.append((frame, f"  [{t:.2f}s in clip]"))
    return result


def _fallback(scene: dict, target_cut_s: float, reason: str) -> dict:
    # For fallback, center the window on key_moment_s if available, otherwise true midpoint.
    key_moment = scene.get("key_moment_s")
    if key_moment is not None:
        center = max(scene["start_s"], min(key_moment, scene["end_s"]))
    else:
        center = (scene["start_s"] + scene["end_s"]) / 2

    hint = scene.get("duration_hint", "normal")
    hinted_target = target_cut_s * HINT_MULTIPLIERS.get(hint, 1.0)
    effective_target = min(hinted_target, HOOK_MAX_CUT_S) if scene.get("is_hook") else hinted_target
    half = effective_target / 2
    start_s = round(max(scene["start_s"], center - half), 3)
    end_s = round(min(scene["end_s"], start_s + max(effective_target, MIN_CUT_S)), 3)
    if end_s - start_s < MIN_CUT_S:
        end_s = round(min(scene["end_s"], start_s + MIN_CUT_S), 3)
    return {
        "scene_id": scene["scene_id"],
        "clip_index": scene["clip_index"],
        "clip_path": scene["clip_path"],
        "start_s": start_s,
        "end_s": end_s,
        "duration_s": round(end_s - start_s, 3),
        "note": f"[key-moment fallback: {reason}]",
        "confidence": 0.0,
    }
