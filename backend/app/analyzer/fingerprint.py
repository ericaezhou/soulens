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
    if not ANTHROPIC_API_KEY:
        return {"error": "No Anthropic API key configured"}

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build a compact but complete representation of all reels
    reels_summary = []
    for i, r in enumerate(reels):
        p = r.get("pacing", {})
        a = r.get("audio", {})
        c = r.get("color", {})
        t = r.get("text", {})
        mo = r.get("motion", {})

        reels_summary.append({
            "reel": i + 1,
            "duration_s": round(r.get("meta", {}).get("duration") or 0, 1),
            "cuts": p.get("cut_count", 0),
            "avg_cut_s": round(p.get("avg_cut_duration", 0), 2),
            "cut_sequence": p.get("cut_durations", [])[:20],  # first 20 cuts
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
            "palette": c.get("dominant_palette", [])[:4],
            "eq_params": c.get("eq_params", {}),
            "has_text": t.get("has_text", False),
            "text_placement": t.get("dominant_placement"),
            "text_timing": t.get("text_timing"),
            "text_hints": t.get("style_hints", []),
            "motion_style": mo.get("motion_style", ""),
            "skin_ratio": round(c.get("skin_ratio", 0), 2),
        })

    prompt = f"""You are an expert video editor analyzing {len(reels)} Instagram Reels from @{username} to build their definitive editing Style Profile.

Here is the full per-reel analysis data:

{json.dumps(reels_summary, indent=2)}

Your job: find the PATTERNS across all these reels — not averages. What does this creator consistently do? What varies? What defines their style?

Respond with a JSON object (raw JSON, no markdown) with these exact keys:

{{
  "style_name": "2-3 word name capturing their editing identity",
  "vibe": "One sentence: what does watching their content feel like?",
  "content_type": "What kind of content (lifestyle, fashion, tutorial, travel, GRWM, etc.)",
  "creator_archetype": "The aesthetic curator / the storyteller / the hype creator / the informer / etc.",

  "pacing_pattern": {{
    "description": "How they structure pacing (e.g. 'fast open 3-5 cuts, slow middle, fast close')",
    "opening_cuts": "How they open — fast or slow, how many cuts in first 3s",
    "body_rhythm": "Pacing in the middle section",
    "closing_style": "How they end — fade, hard cut, slow down",
    "target_avg_cut_s": <float, the cut duration their edits should target>,
    "target_variation": <float 0-1, how much variation to add: 0=robotic, 0.3=natural, 0.6=dynamic>,
    "beat_sync_strength": <float 0-1, how strongly to sync cuts to beats>
  }},

  "color_recipe": {{
    "description": "Their color philosophy in plain English",
    "grade_style": "<one of: vibrant_warm | vibrant_cool | desaturated_moody | faded_film | bright_airy | dark_moody | high_contrast_punchy | golden_warm | cool_teal | natural_balanced>",
    "eq_brightness": <float -0.5 to 0.5, FFmpeg brightness adjustment>,
    "eq_contrast": <float 0.5 to 3.0, FFmpeg contrast multiplier>,
    "eq_saturation": <float 0.0 to 3.0, FFmpeg saturation multiplier>,
    "eq_r_gain": <float 0.5 to 2.0, red channel gain for warmth>,
    "eq_b_gain": <float 0.5 to 2.0, blue channel gain for cool>,
    "consistent_across_reels": <true/false>
  }},

  "text_recipe": {{
    "uses_text": <true/false>,
    "placement": "<lower_third | upper_third | center | none>",
    "timing": "<throughout | early_hook | periodic | sparse | none>",
    "style": "<all_caps_bold | mixed_case | minimal | heavy>",
    "description": "How and when they use text overlays"
  }},

  "structure_template": {{
    "description": "Their typical reel structure from start to finish",
    "hook_duration_s": <float, how long their hook section typically is>,
    "hook_style": "What they do in the hook to grab attention",
    "body_structure": "What happens in the main body",
    "outro_style": "How they close",
    "target_total_duration_s": <float, ideal output duration>
  }},

  "signature_moves": ["3-5 specific techniques that define their editing"],
  "avoid": ["2-3 things that would break their style"],

  "replication_instructions": [
    "Step-by-step instructions for editing new footage in this exact style — be specific and actionable, not generic"
  ]
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
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
