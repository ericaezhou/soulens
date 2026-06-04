"""
Phase 2: Paper Edit.

Text-only Claude call — no images. Receives the scene catalog from Phase 1
and the creator's style profile. Selects which scenes to keep and identifies
the hook moment. Does NOT reorder — shooting order is preserved by the caller,
with the hook scene duplicated to front as a short tease.

Output schema:
  hook_scene_id  — scene_id of the best hook moment (will be duplicated to front)
  drop           — scene_ids to exclude (redundant, weak, incomplete, over-budget)
  reasoning      — 3-4 sentence plan shown in the Paper Edit Review UI
"""
import re
import json
from app.llm import create_message


def plan_edit(scenes: list[dict], profile: dict, feedback: str = "", current_selection: dict | None = None) -> dict:
    username = profile.get("username", "this creator")
    synthesis = profile.get("synthesis", {})
    total_dur = sum(s["duration_s"] for s in scenes)
    catalog_text = _build_catalog_text(scenes)
    style_text = _build_style_text(synthesis)

    any_face = any(s.get("face_visible", False) for s in scenes)

    feedback_block = ""
    if feedback.strip():
        current_block = ""
        if current_selection:
            kept_ids = [s["scene_id"] for s in current_selection.get("scenes", [])
                        if not s.get("scene_id", "").endswith("_hook")]
            hook_id = current_selection.get("hook_scene_id", "")
            current_block = (
                f"CURRENT SELECTION:\n"
                f"  Hook: {hook_id}\n"
                f"  Kept scenes (in order): {', '.join(kept_ids)}\n\n"
            )
        feedback_block = (
            current_block
            + f"CREATOR FEEDBACK: \"{feedback.strip()}\"\n"
            f"Adjust the current selection based on this feedback. "
            f"Only change what is necessary to satisfy the feedback — keep everything else the same. "
            f"Do not drop scenes that were not mentioned in the feedback.\n\n"
        )

    prompt = (
        feedback_block
        + f"You are selecting clips for an Instagram Reel for @{username}.\n\n"
        f"CREATOR STYLE:\n{style_text}\n\n"
        f"SCENE CATALOG ({len(scenes)} scenes, {total_dur:.1f}s total):\n{catalog_text}\n\n"
        "IMPORTANT: The clips are numbered by the order they were filmed. "
        "Your job is to SELECT, not reorder — the shooting order will be preserved. "
        "The hook scene will be shown as a short 2-second tease at the very front, "
        "then the full edit plays in filmed order.\n\n"
        "Rules:\n"
        "  - hook_scene_id: the single most visually striking moment for the opening tease "
        "(it also stays in its natural position in the body — do not put it in drop)\n"
        "  - Narrative arc: use the arc in CREATOR STYLE as a preference compass when choosing what to keep. "
        "When two scenes are similar quality, prefer the one that fills the next unfilled story beat. "
        "But quality comes first — never keep a low-energy or incomplete-action scene just to fill a slot. "
        "Skip a beat gracefully rather than using weak footage as filler. "
        "The arc shapes personality; quality keeps it watchable.\n"
        "  - Money shot: if any scene matches the money shot description, always keep it — "
        "it is the visual anchor of the reel.\n"
        "  - drop: Drop a scene if (a) another kept scene already shows the same subject in a better shot "
        "(higher energy, complete action, closer framing), OR (b) it adds no new visual information. "
        "Two scenes with the same intent tag are NOT automatically redundant if their subjects differ — "
        "each distinct subject adds its own beat. But if the same dish/ingredient appears twice, "
        "keep only the best shot — do NOT show the same food item twice in the reel. "
        "Also drop scenes where action_complete=false if a complete version of that same action exists. "
        "Prefer one great shot of each subject over two adequate shots of the same thing.\n"
        "  - Keep at least one establishment scene so the viewer has context before the payoff. "
        "Keep at least one payoff scene — the money shot matters\n"
        + (
            "  - At least one face-visible scene exists — try to keep one for viewer connection\n"
            if any_face else ""
        )
        + "  - reasoning: 3-4 sentences — why this hook, what you kept vs dropped and why "
        "(reference intent/subject when explaining drops), "
        "how the remaining scenes tell a complete story in their natural order\n"
        "  - duration_hints: assign one timing category to every kept scene (omit dropped scenes):\n"
        '      "fast"    — walking shots, crowd context, transition B-roll, action the viewer already understands\n'
        '      "normal"  — standard process shots, generic B-roll without strong narrative weight\n'
        '      "breathe" — first cultural/historical context after the hook, wide space/spread reveals,\n'
        "                  any scene that needs a beat to land before the next cut\n"
        '      "long"    — the hero/money shot (steam rising, food lifted, first bite), visible creator\n'
        "                  emotion, direct eye contact. Use sparingly — one or two per edit.\n\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        '  "hook_scene_id": "<scene_id>",\n'
        '  "drop": ["<scene_id>", ...],\n'
        '  "duration_hints": {"<scene_id>": "fast|normal|breathe|long", ...},\n'
        '  "narrative_summary": "<2-3 sentences describing the edit flow in content terms — what the viewer sees, in order. No scene IDs or clip numbers. Example: \'Opens with a dramatic cheese pull tease, moves through the banchan spread and kimbap lift, closes with a face reaction.\'>",\n'
        '  "reasoning": "<Plain-language explanation of what was kept and what was dropped, and why — reference subjects by name (e.g. \'the kiosk shot\', \'the stirring close-up\'), never by clip or scene ID. 3-5 sentences.>"\n'
        "}"
    )

    text = create_message(prompt if isinstance(prompt, list) else [{"type": "text", "text": prompt}], max_tokens=2048).strip()
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"Paper edit returned no JSON: {text[:300]}")

    json_str = match.group()
    try:
        result = json.loads(json_str)
    except json.JSONDecodeError:
        json_str = re.sub(r"[\x00-\x1f\x7f]", " ", json_str)
        result = json.loads(json_str)

    valid_ids = {s["scene_id"] for s in scenes}
    result["drop"] = [sid for sid in result.get("drop", []) if sid in valid_ids]

    # Hook must not be in the drop list
    hook_id = result.get("hook_scene_id", "")
    if hook_id in result["drop"]:
        result["drop"].remove(hook_id)

    return result


def _build_catalog_text(scenes: list[dict]) -> str:
    lines = []
    for s in scenes:
        energy_dot = "●" if s["energy"] == "high" else "◑" if s["energy"] == "medium" else "○"
        intent = s.get("intent", "process")
        subject = s.get("subject", "")
        action_complete = s.get("action_complete", True)
        face = " 👤" if s.get("face_visible") else ""
        camera = s.get("camera_motion", "static")
        incomplete = " [incomplete action]" if not action_complete else ""

        lines.append(
            f"  [{s['scene_id']}] {intent.upper()} · {s['shot_type']} · {s['duration_s']:.1f}s · "
            f"{energy_dot} {s['energy']}{face} · {camera}{incomplete}\n"
            f"    Subject: {subject}\n"
            f"    {s.get('description', '')}\n"
            f"    Start: {s.get('start_state', '')} | End: {s.get('end_state', '')}"
        )
    return "\n".join(lines)


def _build_style_text(synthesis: dict) -> str:
    lines = []
    if synthesis.get("hook_formula"):
        lines.append(f"Hook formula: {synthesis['hook_formula']}")

    narrative = synthesis.get("cooking_narrative", {})

    sequence = narrative.get("sequence", [])
    if sequence:
        beats = "\n".join(f"  {i+1}. {beat}" for i, beat in enumerate(sequence))
        lines.append(
            "Narrative arc (preference compass — quality over slot-filling; skip beats with no strong scene):\n"
            + beats
        )

    if narrative.get("pacing_within_steps"):
        lines.append(f"Pacing nuance: {narrative['pacing_within_steps']}")

    if narrative.get("money_shot"):
        lines.append(f"Money shot (always keep if a quality scene exists): {narrative['money_shot']}")

    if narrative.get("what_they_skip"):
        lines.append(f"Skip content: {narrative['what_they_skip']}")

    pacing = synthesis.get("pacing_pattern", {})
    if pacing.get("description"):
        lines.append(f"Pacing: {pacing['description']}")
    if pacing.get("target_avg_cut_s"):
        lines.append(f"Avg cut: {pacing['target_avg_cut_s']}s")
    if synthesis.get("signature_moves"):
        lines.append(f"Signature: {', '.join(synthesis['signature_moves'])}")
    if synthesis.get("avoid"):
        lines.append(f"Avoid: {', '.join(synthesis['avoid'])}")
    return "\n".join(lines) if lines else "Fast-paced, punchy cuts."
