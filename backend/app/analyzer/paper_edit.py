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
from app.llm import get_client, claude_model


def plan_edit(scenes: list[dict], profile: dict) -> dict:
    username = profile.get("username", "this creator")
    synthesis = profile.get("synthesis", {})
    total_dur = sum(s["duration_s"] for s in scenes)
    catalog_text = _build_catalog_text(scenes)
    style_text = _build_style_text(synthesis)

    # Check if any scene has a visible face — used to give Claude the right constraint
    any_face = any(s.get("face_visible", False) for s in scenes)

    prompt = (
        f"You are selecting clips for an Instagram Reel for @{username}.\n\n"
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
        "  - drop: ONLY drop a scene if another kept scene already shows the exact same subject "
        "doing the exact same action — use the Subject field to judge. "
        "Two scenes with the same intent tag are NOT automatically redundant if their subjects differ; "
        "each distinct subject adds its own beat to the story. "
        "Drop a scene only when keeping it would show the viewer nothing new. "
        "Also drop scenes where action_complete=false ONLY if a complete version of that same action exists. "
        "When in doubt, keep — a missing visual beat is worse than a reel that runs a few seconds long\n"
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
        '  "reasoning": "<3-4 sentence plan>"\n'
        "}"
    )

    client = get_client()

    response = client.messages.create(
        model=claude_model(),
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
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
