"""
Generates spoken script + caption plan grounded in the actual visual edit.

Accepts catalog_cuts — the Phase 3 precision cuts enriched with Phase 1 metadata
(intent, subject, description, start_state, end_state) and their absolute timestamps
in the final edit. This lets Claude write narration that syncs beat-by-beat with
what's on screen rather than reasoning from generic scene timing alone.
"""
import re
import json
from app.llm import get_client, claude_model


def generate_script_and_captions(
    style_profile: dict,
    catalog_cuts: list[dict],
    footage_duration: float,
    footage_topic: str = "",
) -> dict:
    """
    style_profile   : full profile dict (synthesis + edit_recipe)
    catalog_cuts    : list of dicts — each cut has:
                        edit_start_s, edit_end_s, duration_s (position in final edit)
                        intent, subject, description, start_state, end_state (Phase 1)
    footage_duration: total seconds of the final edit
    footage_topic   : optional topic hint from user
    """

    synthesis = style_profile.get("synthesis", {})
    recipe = style_profile.get("edit_recipe", {})
    username = style_profile.get("username", "this creator")

    target_duration = recipe.get("target_duration_s", 25.0)
    hook_duration = recipe.get("hook_duration_s", 3.0)
    text_recipe = synthesis.get("text_recipe", {})
    structure = synthesis.get("structure_template", {})
    verbal = synthesis.get("verbal_style", {})

    beat_lines = _build_beat_sheet(catalog_cuts)
    voice_block = _build_voice_block(verbal, style_profile.get("voice_samples", []))

    prompt = (
        f"You are ghostwriting an Instagram Reel script for @{username}. "
        f"Your job is to sound exactly like them — not like a generic creator.\n\n"
        "CREATOR VOICE & STYLE:\n"
        f"  Archetype: {synthesis.get('creator_archetype', '')}\n"
        f"  Vibe: {synthesis.get('vibe', '')}\n"
    )

    if verbal:
        prompt += (
            f"  Speaks to camera: {verbal.get('speaks_to_camera', True)}\n"
            f"  Sentence length: {verbal.get('sentence_length', '')}\n"
            f"  Tone: {verbal.get('tone', '')}\n"
            f"  Opener pattern: {verbal.get('opener_pattern', '')}\n"
            f"  Closer pattern: {verbal.get('closer_pattern', '')}\n"
            f"  Vocabulary notes: {verbal.get('vocabulary', '')}\n"
        )
        if verbal.get("example_phrases"):
            prompt += f"  Example phrases: {' | '.join(verbal['example_phrases'])}\n"

    if voice_block:
        prompt += f"\nACTUAL TRANSCRIPT SAMPLES (their real words — study the cadence and vocabulary):\n{voice_block}\n"

    prompt += (
        f"\nEDIT STRUCTURE:\n"
        f"  Hook style: {structure.get('hook_style', '')}\n"
        f"  Body structure: {structure.get('body_structure', '')}\n"
        f"  Outro style: {structure.get('outro_style', '')}\n"
        f"  Text overlays: {text_recipe.get('description', 'minimal')}\n"
        f"  Text style: {text_recipe.get('style', 'minimal')}\n"
    )

    if synthesis.get("signature_moves"):
        prompt += f"  Signature moves: {', '.join(synthesis['signature_moves'])}\n"
    if synthesis.get("avoid"):
        prompt += f"  Avoid: {', '.join(synthesis['avoid'])}\n"

    prompt += (
        f"\nVISUAL BEAT SHEET (what's on screen in this edit, in order):\n"
        f"{beat_lines}\n\n"
        f"Edit duration: {footage_duration:.1f}s  |  Target reel: ~{target_duration:.0f}s  |  "
        f"Hook window: first {hook_duration:.0f}s\n"
    )

    if footage_topic:
        prompt += f"Topic/context: {footage_topic}\n"

    max_words = int(footage_duration * 2.5)

    prompt += (
        f"\nSCRIPT CONSTRAINTS:\n"
        f"  Max words (full_script): {max_words} — at ~150 WPM this fills {footage_duration:.0f}s comfortably. "
        f"Going over makes the voiceover feel rushed.\n\n"
        "\nWrite a spoken script that narrates THESE SPECIFIC VISUALS in @{username}'s voice. "
        "Sync your narration to what's actually shown — reference specific subjects, "
        "actions, and transitions from the beat sheet. The hook (first {hook_duration:.0f}s) should "
        "match the opening visual beat. Caption timestamps must align with the visual beats above.\n\n"
        "Return ONLY valid JSON:\n"
        "{{\n"
        '  "spoken_script": {{\n'
        '    "hook": "Exact words for the first {hook_duration:.0f}s — must match the opening visual",\n'
        '    "body": "Narration through the main section — reference the specific things shown",\n'
        '    "cta": "Their natural call-to-action style",\n'
        '    "full_script": "Complete script hook→body→cta as one flowing block",\n'
        '    "tone_notes": "1-2 sentences on tone/energy for delivery"\n'
        "  }},\n"
        '  "caption_plan": [\n'
        "    {{\n"
        '      "timestamp_s": <float — must match a visual beat start time from the beat sheet>,\n'
        '      "duration_s": <float>,\n'
        '      "text": "Exact overlay text",\n'
        '      "placement": "<lower_third | upper_third | center>",\n'
        '      "style_note": "bold/minimal/all-caps etc."\n'
        "    }}\n"
        "  ],\n"
        '  "hashtag_suggestions": ["5-8 relevant hashtags"],\n'
        '  "reel_caption": "Instagram caption in their typical style"\n'
        "}}"
    ).format(username=username, hook_duration=hook_duration)

    client = get_client()
    try:
        response = client.messages.create(
            model=claude_model(),
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        text = re.sub(r"```(?:json)?\s*", "", text).strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {"error": f"Scriptwriter returned no JSON: {text[:300]}"}
        json_str = re.sub(r"[\x00-\x1f\x7f]", " ", match.group())
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        return {"error": f"Claude returned invalid JSON: {e}"}
    except Exception as e:
        return {"error": str(e)}


def _build_voice_block(verbal: dict, voice_samples: list[str]) -> str:
    """
    Build a compact voice reference block from real transcript samples.
    Prefers the synthesized example_phrases from verbal_style (new profiles);
    falls back to the raw voice_samples saved during profile synthesis.
    """
    examples = verbal.get("example_phrases", [])
    if examples:
        return "\n".join(f'  "{p}"' for p in examples)

    return "\n".join(f'  "{s[:150]}"' for s in voice_samples if s.strip())


def _build_beat_sheet(catalog_cuts: list[dict]) -> str:
    lines = []
    for cut in catalog_cuts:
        t_start = cut.get("edit_start_s", 0.0)
        t_end = cut.get("edit_end_s", t_start + cut.get("duration_s", 0.0))
        intent = cut.get("intent", "process").upper()
        subject = cut.get("subject", "")
        description = cut.get("description", "")
        start_state = cut.get("start_state", "")
        end_state = cut.get("end_state", "")
        shot = cut.get("shot_type", "")
        energy = cut.get("energy", "")

        detail = description or f"{start_state} → {end_state}"
        lines.append(
            f"  {t_start:.2f}s–{t_end:.2f}s [{intent}] {shot} · {subject}"
            + (f" | {detail}" if detail.strip(" → ") else "")
            + (f" ({energy} energy)" if energy else "")
        )
    return "\n".join(lines) if lines else "  (no scene data available)"
