"""
Synthesizes analysis from 20 reels into one Style Profile via Claude.
The output is machine-actionable — it drives the editor directly.
"""
import json
import anthropic
from app.config import ANTHROPIC_API_KEY


def synthesize_style_profile(username: str, reels: list[dict]) -> dict:
    """
    Takes per-reel analysis data for up to 20 reels.
    Returns a Style Profile: Claude's synthesis + an edit recipe the engine executes.
    """
    successful = [r for r in reels if "error" not in r]
    if not successful:
        raise ValueError("No successfully analyzed reels to synthesize.")

    claude_synthesis = _call_claude(username, successful)
    edit_recipe = _extract_edit_recipe(claude_synthesis, successful)

    return {
        "username": username,
        "reels_used": len(successful),
        "synthesis": claude_synthesis,
        "edit_recipe": edit_recipe,
    }


def _call_claude(username: str, reels: list[dict]) -> dict:
    from dotenv import load_dotenv
    import os as _os
    load_dotenv(override=True)
    api_key = _os.getenv("ANTHROPIC_API_KEY", "") or ANTHROPIC_API_KEY
    if not api_key:
        return {"error": "No Anthropic API key configured"}

    client = anthropic.Anthropic(api_key=api_key)

    # Build compact measurement summaries
    reels_summary = []
    for i, r in enumerate(reels):
        p = r.get("pacing", {})
        a = r.get("audio", {})
        c = r.get("color", {})
        mo = r.get("motion", {})
        tr = r.get("transcript", {})
        reels_summary.append({
            "reel": i + 1,
            "duration_s": round(r.get("meta", {}).get("duration") or 0, 1),
            "cuts": p.get("cut_count", 0),
            "avg_cut_s": round(p.get("avg_cut_duration", 0), 2),
            "cut_sequence": p.get("cut_durations", [])[:20],
            "rhythm": p.get("rhythm", ""),
            "pacing_variation": round(p.get("pacing_variation", 0), 2),
            "bpm": round(a.get("bpm", 0)),
            "beat_sync": round(r.get("beat_sync_ratio", 0), 2),
            "music_intensity": a.get("music_intensity", ""),
            "color_grade": c.get("grade_style", ""),
            "saturation": round(c.get("saturation", 0), 2),
            "brightness": round(c.get("brightness", 0), 2),
            "contrast": round(c.get("contrast", 0), 2),
            "warmth": round(c.get("warmth", 0), 3),
            "eq_params": c.get("eq_params", {}),
            "motion_style": mo.get("motion_style", ""),
            "has_speech": tr.get("has_speech", False),
            "speech_transcript": tr.get("transcript", "")[:400],
        })

    # Build multimodal content: measurements + key frames per reel
    content = []
    content.append({"type": "text", "text": (
        f"You are a professional video editor building a definitive Style Profile for @{username} "
        f"by analyzing {len(reels)} of their Instagram Reels.\n\n"
        f"You have three inputs per reel:\n"
        f"1. Precise measurements (cut timing, color values, BPM, motion)\n"
        f"2. Speech transcript from Whisper audio transcription (what the creator says/captions)\n"
        f"3. Key frames: hook (first scene cut) + 2 body scenes at cut boundaries + outro (4 total per reel)\n\n"
        f"MEASUREMENT DATA (includes speech_transcript per reel):\n{json.dumps(reels_summary, indent=2)}"
    )})

    # Attach frames grouped by reel
    has_frames = any(r.get("frames") for r in reels)
    if has_frames:
        content.append({"type": "text", "text": "\n\nKEY FRAMES (hook / 2 body samples / outro — 4 per reel):"})
        for i, r in enumerate(reels):
            frames = r.get("frames", [])
            if not frames:
                continue
            dur = r.get("meta", {}).get("duration") or 0
            content.append({"type": "text", "text": f"\nReel {i+1} ({dur:.0f}s):"})
            for frame_b64 in frames:
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": frame_b64},
                })

    content.append({"type": "text", "text": f"""

Your job: find PATTERNS across all reels — not averages. What does this creator CONSISTENTLY do?
Look specifically at:
- Shot composition and framing (from the frames)
- How they structure cooking content: what steps they show, what they skip, what order
- Their hook formula: exactly what's in frame 0-3s to grab attention
- Their money shot: the climax/hero visual that makes people save the video
- Pacing rhythm: does it match beat drops, speech, or action?
- Their verbal style: what they say, how they narrate (from speech_transcript), tone and vocabulary
- Text vs. speech: do they caption text or just narrate verbally?

Respond with a JSON object (raw JSON, no markdown):

{{
  "style_name": "2-3 word editing identity (e.g. 'Kinetic Kitchen')",
  "vibe": "One sentence: what does watching their content feel like?",
  "content_type": "Type of content (cooking tutorial, recipe, GRWM, etc.)",
  "creator_archetype": "Their creator persona (e.g. 'the relatable chef', 'the technique teacher')",

  "hook_formula": "Exactly what they do in the first 3 seconds — what's in frame, what text appears, what energy",

  "cooking_narrative": {{
    "description": "How they structure a cooking reel start to finish",
    "sequence": ["ordered list of the steps they show, e.g. 'ingredients reveal', 'prep close-up', 'heat/cook', 'plating', 'first bite'"],
    "what_they_skip": "What parts of cooking they cut out entirely",
    "money_shot": "Their go-to hero shot — what it looks like and when it appears",
    "pacing_within_steps": "Do they linger on certain steps? Which ones and why?"
  }},

  "visual_identity": {{
    "shot_composition": "How they frame shots — POV, overhead, eye-level, close-up ratio",
    "camera_work": "Handheld, static, dolly moves, etc.",
    "lighting_style": "What their lighting looks like (natural, warm kitchen, moody, bright studio)",
    "transition_style": "How they cut between shots (hard cut, match cut, whip pan, etc.)"
  }},

  "pacing_pattern": {{
    "description": "How pacing flows across the reel",
    "opening_cuts": "Hook pacing — fast or slow, how many cuts in first 3s",
    "body_rhythm": "Pacing in the cooking body",
    "closing_style": "How they end",
    "target_avg_cut_s": <float>,
    "target_variation": <float 0-1>,
    "beat_sync_strength": <float 0-1>
  }},

  "color_recipe": {{
    "description": "Their color philosophy — warm kitchen glow? Clean bright studio? Moody dark?",
    "grade_style": "<vibrant_warm|vibrant_cool|desaturated_moody|faded_film|bright_airy|dark_moody|high_contrast_punchy|golden_warm|cool_teal|natural_balanced>",
    "eq_brightness": <float -0.5 to 0.5>,
    "eq_contrast": <float 0.5 to 3.0>,
    "eq_saturation": <float 0.0 to 3.0>,
    "eq_r_gain": <float 0.5 to 2.0>,
    "eq_b_gain": <float 0.5 to 2.0>,
    "consistent_across_reels": <true/false>
  }},

  "text_recipe": {{
    "uses_text": <true/false>,
    "placement": "<lower_third|upper_third|center|none>",
    "timing": "<throughout|early_hook|periodic|sparse|none>",
    "style": "<all_caps_bold|mixed_case|minimal|heavy>",
    "description": "What info they put in text vs. say out loud (inferred from frames and transcript)"
  }},

  "structure_template": {{
    "description": "Full reel structure start to finish",
    "hook_duration_s": <float>,
    "hook_style": "What the hook looks/feels like",
    "body_structure": "How the cooking middle section is structured",
    "outro_style": "How they close",
    "target_total_duration_s": <float>
  }},

  "signature_moves": ["4-6 specific techniques that make their editing unmistakably theirs"],
  "avoid": ["3 things that would immediately break their style"],

  "replication_instructions": [
    "Specific, actionable step-by-step instructions for editing new raw cooking footage in this exact style"
  ]
}}"""})

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            messages=[{"role": "user", "content": content}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"Claude returned invalid JSON: {e}"}
    except Exception as e:
        return {"error": str(e)}


def _extract_edit_recipe(synthesis: dict, reels: list[dict]) -> dict:
    """
    Pull the machine-actionable parameters out of Claude's synthesis.
    This is what the editor engine actually uses.
    """
    pacing = synthesis.get("pacing_pattern", {})
    color = synthesis.get("color_recipe", {})
    text = synthesis.get("text_recipe", {})
    structure = synthesis.get("structure_template", {})

    # Average the eq_params across reels as a fallback if Claude didn't produce values
    avg_eq = _average_eq_params(reels)

    return {
        # Pacing
        "target_cut_duration": pacing.get("target_avg_cut_s") or avg_eq.get("avg_cut", 2.0),
        "cut_variation": pacing.get("target_variation") or 0.3,
        "beat_sync_strength": pacing.get("beat_sync_strength") or 0.5,
        "opening_style": pacing.get("opening_cuts", "fast"),
        "closing_style": pacing.get("closing_style", "hard_cut"),

        # Structure
        "hook_duration_s": structure.get("hook_duration_s") or 3.0,
        "target_duration_s": structure.get("target_total_duration_s") or 25.0,
        "hook_style": structure.get("hook_style", ""),

        # Color — Claude's values take priority, fall back to averaged measurements
        "color": {
            "brightness": color.get("eq_brightness") if color.get("eq_brightness") is not None else avg_eq["brightness"],
            "contrast": color.get("eq_contrast") if color.get("eq_contrast") is not None else avg_eq["contrast"],
            "saturation": color.get("eq_saturation") if color.get("eq_saturation") is not None else avg_eq["saturation"],
            "r_gain": color.get("eq_r_gain") if color.get("eq_r_gain") is not None else avg_eq["r_gain"],
            "b_gain": color.get("eq_b_gain") if color.get("eq_b_gain") is not None else avg_eq["b_gain"],
        },
        "grade_style": color.get("grade_style", "natural_balanced"),

        # Text
        "add_text": text.get("uses_text", False),
        "text_placement": text.get("placement", "lower_third"),
        "text_style": text.get("style", "minimal"),
    }


def _average_eq_params(reels: list[dict]) -> dict:
    """Fallback: average the measured eq params across all reels."""
    keys = ["brightness", "contrast", "saturation", "r_gain", "b_gain"]
    totals = {k: 0.0 for k in keys}
    totals["avg_cut"] = 0.0
    count = 0

    for r in reels:
        eq = r.get("color", {}).get("eq_params", {})
        if not eq:
            continue
        for k in keys:
            totals[k] += eq.get(k, 0)
        totals["avg_cut"] += r.get("pacing", {}).get("avg_cut_duration", 2.0)
        count += 1

    if count == 0:
        return {"brightness": 0, "contrast": 1, "saturation": 1, "r_gain": 1, "b_gain": 1, "avg_cut": 2.0}

    return {k: round(totals[k] / count, 3) for k in list(keys) + ["avg_cut"]}
