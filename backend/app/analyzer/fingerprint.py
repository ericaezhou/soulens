import json
import anthropic
from app.config import ANTHROPIC_API_KEY


def build_fingerprint(
    scenes: list[dict],
    pacing: dict,
    audio: dict,
    color: dict,
    text: dict,
    motion: dict,
    video_meta: dict,
) -> dict:
    beat_sync_ratio = _calculate_beat_sync(scenes, audio.get("beat_times", []))

    fingerprint = {
        "meta": {
            "duration": video_meta.get("duration"),
            "uploader": video_meta.get("uploader", ""),
            "title": video_meta.get("title", ""),
            "width": video_meta.get("width"),
            "height": video_meta.get("height"),
            "fps": video_meta.get("fps"),
        },
        "pacing": pacing,
        "audio": audio,
        "color": color,
        "text": text,
        "motion": motion,
        "beat_sync_ratio": round(beat_sync_ratio, 3),
        "scenes": scenes[:50],  # Keep first 50 for reference
    }

    fingerprint["interpretation"] = _interpret_with_claude(fingerprint)
    fingerprint["edit_recipe"] = _build_edit_recipe(fingerprint)

    return fingerprint


def _calculate_beat_sync(scenes: list[dict], beat_times: list[float]) -> float:
    if not scenes or not beat_times:
        return 0.0

    cut_times = [s["start_time"] for s in scenes[1:]]
    if not cut_times:
        return 0.0

    synced = 0
    for cut in cut_times:
        for beat in beat_times:
            if abs(cut - beat) < 0.25:
                synced += 1
                break

    return synced / len(cut_times)


def _interpret_with_claude(fingerprint: dict) -> dict:
    if not ANTHROPIC_API_KEY:
        return {"error": "No Anthropic API key configured"}

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    pacing = fingerprint["pacing"]
    audio = fingerprint["audio"]
    color = fingerprint["color"]
    text = fingerprint["text"]
    motion = fingerprint["motion"]
    meta = fingerprint["meta"]

    prompt = f"""You are an expert video editor and content strategist analyzing the editing style of an Instagram reel.

Here is the raw analysis data:

CREATOR: {meta.get('uploader', 'Unknown')}
DURATION: {meta.get('duration', 0):.1f}s

PACING:
- Average cut: {pacing.get('avg_cut_duration', 0):.2f}s
- Total cuts: {pacing.get('cut_count', 0)}
- Rhythm: {pacing.get('rhythm', 'unknown')}
- Pacing variation: {pacing.get('pacing_variation', 0):.2f} (0=robotic, 1=organic)
- Fastest cut: {pacing.get('fastest_cut', 0):.2f}s
- Slowest cut: {pacing.get('slowest_cut', 0):.2f}s

AUDIO:
- BPM: {audio.get('bpm', 0):.0f}
- Music intensity: {audio.get('music_intensity', 'unknown')}
- Beat count: {audio.get('beat_count', 0)}
- Dynamic range: {audio.get('dynamic_range', 0):.2f}

BEAT SYNC: {fingerprint.get('beat_sync_ratio', 0):.1%} of cuts land on a beat

COLOR:
- Grade style: {color.get('grade_style', 'unknown')}
- Saturation: {color.get('saturation', 0):.2f} (0=gray, 1=vivid)
- Brightness: {color.get('brightness', 0):.2f} (0=dark, 1=bright)
- Contrast: {color.get('contrast', 0):.2f}
- Warmth: {color.get('warmth', 0):.3f} (negative=cool, positive=warm)
- Shadow cast: {color.get('shadow_cast', 'neutral')}
- Highlight cast: {color.get('highlight_cast', 'neutral')}
- Palette: {', '.join(color.get('dominant_palette', []))}

MOTION:
- Style: {motion.get('motion_style', 'unknown')}
- Avg motion score: {motion.get('avg_motion', 0):.1f}
- Skin ratio: {color.get('skin_ratio', 0):.1%} (indicates talking head vs b-roll)

TEXT:
- Has text overlays: {text.get('has_text', False)}
- Placement: {text.get('dominant_placement', 'none')}
- Timing: {text.get('text_timing', 'none')}
- Text hints: {', '.join(text.get('style_hints', []))}
- Samples: {' | '.join(text.get('sample_texts', [])[:3])}

Based on this data, provide a JSON response (NO markdown, raw JSON only) with these exact keys:
{{
  "style_name": "2-3 word catchy name for their style (e.g. 'Golden Hour Vibes', 'Dark Academia Edit', 'Fast Cuts Energy')",
  "vibe": "One punchy sentence describing the overall feel",
  "content_type": "What type of content this is (e.g. lifestyle vlog, GRWM, fashion haul, travel montage, tutorial, aesthetic reel)",
  "creator_archetype": "Which creator archetype this is (e.g. the aesthetic curator, the storyteller, the hype creator, the informer)",
  "editing_traits": ["4-6 specific editing characteristics as bullet points"],
  "color_story": "1-2 sentences about their color philosophy",
  "pacing_description": "1-2 sentences about their rhythm and energy",
  "text_strategy": "1 sentence about how they use (or don't use) text",
  "beat_sync_analysis": "1 sentence about how they relate cuts to music",
  "signature_moves": ["3-4 specific techniques that define their style"],
  "replication_instructions": ["6-8 step-by-step instructions to replicate this exact style when editing new footage"],
  "avoid": ["2-3 things that would break this style"]
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code blocks if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": response.content[0].text if response else ""}
    except Exception as e:
        return {"error": str(e)}


def _build_edit_recipe(fingerprint: dict) -> dict:
    """Machine-readable recipe for the auto-editor to apply this style."""
    color = fingerprint["color"]
    pacing = fingerprint["pacing"]
    audio = fingerprint["audio"]
    text = fingerprint["text"]

    return {
        "target_cut_duration": pacing.get("avg_cut_duration", 2.0),
        "cut_variation": pacing.get("pacing_variation", 0.3),
        "beat_sync": fingerprint.get("beat_sync_ratio", 0) > 0.4,
        "color": color.get("eq_params", {}),
        "grade_style": color.get("grade_style", "natural_balanced"),
        "add_text": text.get("has_text", False),
        "text_placement": text.get("dominant_placement", "lower_third"),
        "text_style": text.get("style_hints", []),
        "target_duration_range": [15, 30],  # Instagram Reel sweet spot
    }
