"""
Generates two things for new footage:
1. A spoken script: hook + body + CTA, written in the creator's voice
2. A caption plan: what text overlays to show, when, and where
"""
import json
import anthropic
from app.config import ANTHROPIC_API_KEY


def generate_script_and_captions(
    style_profile: dict,
    footage_scenes: list[dict],
    footage_duration: float,
    footage_topic: str = "",
) -> dict:
    """
    style_profile: the full profile dict (with synthesis + edit_recipe)
    footage_scenes: scene list from analyzing the raw footage
    footage_duration: total seconds of raw footage
    footage_topic: optional hint from user about what the footage is about
    """
    if not ANTHROPIC_API_KEY:
        return {"error": "No Anthropic API key configured"}

    synthesis = style_profile.get("synthesis", {})
    recipe = style_profile.get("edit_recipe", {})
    username = style_profile.get("username", "this creator")

    target_duration = recipe.get("target_duration_s", 25.0)
    hook_duration = recipe.get("hook_duration_s", 3.0)
    text_recipe = synthesis.get("text_recipe", {})
    structure = synthesis.get("structure_template", {})

    # Describe the footage content from scene analysis
    scene_descriptions = []
    for i, s in enumerate(footage_scenes[:15]):
        scene_descriptions.append(
            f"Scene {i+1}: {s['start_time']:.1f}s–{s['end_time']:.1f}s ({s['duration']:.1f}s)"
        )

    prompt = f"""You are writing content for @{username}, an Instagram Reel creator.

THEIR STYLE PROFILE:
- Content type: {synthesis.get('content_type', 'lifestyle')}
- Creator archetype: {synthesis.get('creator_archetype', '')}
- Vibe: {synthesis.get('vibe', '')}
- Hook style: {structure.get('hook_style', '')}
- Body structure: {structure.get('body_structure', '')}
- Outro style: {structure.get('outro_style', '')}
- Text usage: {text_recipe.get('description', '')}
- Text style: {text_recipe.get('style', 'minimal')}

RAW FOOTAGE:
- Total duration: {footage_duration:.0f}s
- Number of scenes detected: {len(footage_scenes)}
- Scene breakdown: {chr(10).join(scene_descriptions)}
{f'- Topic/context: {footage_topic}' if footage_topic else ''}

TARGET OUTPUT: ~{target_duration:.0f}s reel (hook: first {hook_duration:.0f}s)

Generate a JSON object (raw JSON, no markdown) with:
{{
  "spoken_script": {{
    "hook": "Exact words for the first {hook_duration:.0f} seconds — must grab attention immediately in their voice",
    "body": "What they say/narrate through the main section — match their tone exactly",
    "cta": "Their typical call-to-action style (follow, comment, share — match how they naturally do it)",
    "full_script": "Complete script from hook to CTA as one block, written naturally in their voice",
    "tone_notes": "1-2 sentences describing the tone/energy to deliver this in"
  }},
  "caption_plan": [
    {{
      "timestamp_s": <when this caption appears, float>,
      "duration_s": <how long it stays on screen, float>,
      "text": "Exact text to display",
      "placement": "<lower_third | upper_third | center>",
      "style_note": "bold/minimal/all-caps etc."
    }}
  ],
  "hashtag_suggestions": ["5-8 relevant hashtags in their niche"],
  "reel_caption": "The Instagram caption text they'd post with this reel (their typical caption style)"
}}

Rules:
- Write in @{username}'s voice — match the energy and style from their profile
- The spoken_script should feel natural to read aloud on camera
- caption_plan should only include text if {text_recipe.get('uses_text', True)} (their text usage pattern)
- Space captions naturally — don't overwhelm the screen
- If they don't use text overlays, return an empty caption_plan array"""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
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
