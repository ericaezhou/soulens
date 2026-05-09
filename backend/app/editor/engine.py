"""
Executes an edit plan produced by Claude against raw footage.
Outputs: MP4 + FCPXml process file.
"""
import subprocess
import json
import uuid
import numpy as np
from pathlib import Path

from app.editor.fcpxml import generate_fcpxml


def apply_style(
    footage_path: str,
    style_profile: dict,
    output_dir: Path,
    caption_plan: list[dict] | None = None,
    candidate_clips: list[dict] | None = None,
) -> dict:
    recipe = style_profile.get("edit_recipe", {})

    output_stem = f"edit_{uuid.uuid4()}"
    mp4_path = output_dir / f"{output_stem}.mp4"
    fcpxml_path = output_dir / f"{output_stem}.fcpxml"

    probe = _probe_video(footage_path)
    if not probe:
        raise ValueError("Cannot read footage file")

    duration = probe["duration"]

    if candidate_clips:
        # Use real scene timestamps from rough cut Pass 1
        cuts = _clips_to_cuts(candidate_clips, recipe)
    else:
        # Fallback: mathematical cuts from style parameters
        cuts = _generate_cuts(
            total_duration=duration,
            target_duration=recipe.get("target_duration_s", 25.0),
            avg_cut=recipe.get("target_cut_duration", 2.0),
            variation=recipe.get("cut_variation", 0.3),
            beat_sync_strength=recipe.get("beat_sync_strength", 0.5),
            hook_duration=recipe.get("hook_duration_s", 3.0),
        )

    color = recipe.get("color", {})
    color_filter = _build_color_filter(color)

    # Render MP4
    cmd = _build_ffmpeg_cmd(footage_path, str(mp4_path), cuts, color_filter, caption_plan)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {result.stderr[-800:]}")

    # Generate FCPXml — clips get the same color recipe applied
    clips_with_color = [dict(c, color=color) for c in cuts]
    generate_fcpxml(
        clips=clips_with_color,
        source_path=str(Path(footage_path).resolve()),
        output_path=str(fcpxml_path),
        project_name=f"auto-edit-{style_profile.get('username', 'profile')}",
        caption_plan=caption_plan,
    )

    return {
        "mp4_path": str(mp4_path),
        "fcpxml_path": str(fcpxml_path),
        "mp4_filename": mp4_path.name,
        "fcpxml_filename": fcpxml_path.name,
        "cuts_applied": len(cuts),
        "output_duration_s": round(sum(c["duration"] for c in cuts), 2),
        "grade_style": recipe.get("grade_style", "natural_balanced"),
        "file_size_bytes": mp4_path.stat().st_size if mp4_path.exists() else 0,
    }


def _probe_video(path: str) -> dict | None:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None

    data = json.loads(result.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        return None

    duration = float(data.get("format", {}).get("duration", 0))
    fps_str = video.get("r_frame_rate", "30/1")
    try:
        n, d = fps_str.split("/")
        fps = float(n) / float(d)
    except Exception:
        fps = 30.0

    return {"duration": duration, "fps": fps, "width": int(video.get("width", 1080)), "height": int(video.get("height", 1920))}


def _clips_to_cuts(candidate_clips: list[dict], recipe: dict) -> list[dict]:
    """
    Convert rough cut candidates into the cuts list ffmpeg needs.
    Trims to target duration, applies hook pacing to the first few clips.
    """
    target_duration = recipe.get("target_duration_s", 25.0)
    hook_duration = recipe.get("hook_duration_s", 3.0)

    cuts = []
    accumulated = 0.0

    for i, clip in enumerate(candidate_clips):
        remaining = target_duration - accumulated
        if remaining <= 0.2:
            break

        start = clip["start_time"]
        clip_dur = min(clip["duration"], remaining)

        # Hook clips: shorten them to match the creator's hook pacing
        if accumulated < hook_duration:
            clip_dur = min(clip_dur, hook_duration / max(1, sum(
                1 for c in candidate_clips
                if c["start_time"] < hook_duration
            )))

        clip_dur = max(0.2, clip_dur)
        end = start + clip_dur

        cuts.append({"start": round(start, 3), "end": round(end, 3), "duration": round(clip_dur, 3)})
        accumulated += clip_dur

    return cuts


def _generate_cuts(
    total_duration: float,
    target_duration: float,
    avg_cut: float,
    variation: float,
    beat_sync_strength: float,
    hook_duration: float,
) -> list[dict]:
    rng = np.random.default_rng(42)
    cuts = []
    t = 0.0
    accumulated = 0.0

    while t < total_duration - 0.3 and accumulated < target_duration:
        remaining_target = target_duration - accumulated

        if t < hook_duration:
            # Hook: shorter, punchier cuts
            cut_len = avg_cut * 0.6
        elif remaining_target < avg_cut * 1.5:
            # Outro: let it breathe a bit
            cut_len = min(remaining_target, avg_cut * 1.3)
        else:
            spread = avg_cut * variation
            cut_len = float(np.clip(rng.normal(avg_cut, spread), avg_cut * 0.4, avg_cut * 2.2))

        end = min(t + cut_len, total_duration)
        actual_dur = end - t

        if actual_dur < 0.2:
            break

        cuts.append({"start": round(t, 3), "end": round(end, 3), "duration": round(actual_dur, 3)})
        accumulated += actual_dur
        t = end

    return cuts


def _build_color_filter(color: dict) -> str:
    brightness = max(-0.5, min(0.5, color.get("brightness", 0)))
    contrast = max(0.5, min(3.0, color.get("contrast", 1.0)))
    saturation = max(0.0, min(3.0, color.get("saturation", 1.0)))
    r_gain = max(0.5, min(2.0, color.get("r_gain", 1.0)))
    b_gain = max(0.5, min(2.0, color.get("b_gain", 1.0)))

    parts = [f"eq=brightness={brightness:.3f}:contrast={contrast:.3f}:saturation={saturation:.3f}"]
    if abs(r_gain - 1.0) > 0.02 or abs(b_gain - 1.0) > 0.02:
        parts.append(f"colorchannelmixer=rr={r_gain:.3f}:bb={b_gain:.3f}")
    return ",".join(parts)


def _build_ffmpeg_cmd(
    input_path: str,
    output_path: str,
    cuts: list[dict],
    color_filter: str,
    caption_plan: list[dict] | None,
) -> list[str]:
    if not cuts:
        return ["ffmpeg", "-i", input_path, "-vf", color_filter,
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k", output_path, "-y"]

    n = len(cuts)
    filter_parts = []
    for i, cut in enumerate(cuts):
        s, dur = cut["start"], cut["duration"]
        filter_parts.append(
            f"[0:v]trim=start={s:.3f}:duration={dur:.3f},setpts=PTS-STARTPTS,{color_filter}[v{i}];"
            f"[0:a]atrim=start={s:.3f}:duration={dur:.3f},asetpts=PTS-STARTPTS[a{i}];"
        )

    v_in = "".join(f"[v{i}]" for i in range(n))
    a_in = "".join(f"[a{i}]" for i in range(n))
    filter_complex = (
        "".join(filter_parts)
        + f"{v_in}concat=n={n}:v=1:a=0[outv];"
        + f"{a_in}concat=n={n}:v=0:a=1[outa]"
    )

    # Add text overlays via drawtext if caption plan provided
    if caption_plan:
        drawtext_filters = _build_drawtext(caption_plan)
        if drawtext_filters:
            filter_complex += f";[outv]{drawtext_filters}[outv]"

    return [
        "ffmpeg", "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        output_path, "-y",
    ]


def _build_drawtext(caption_plan: list[dict]) -> str:
    parts = []
    for cap in caption_plan:
        text = cap.get("text", "").replace("'", "\\'").replace(":", "\\:")
        ts = cap.get("timestamp_s", 0)
        dur = cap.get("duration_s", 2.0)
        placement = cap.get("placement", "lower_third")

        y = {"lower_third": "h*0.82", "upper_third": "h*0.1", "center": "(h-text_h)/2"}.get(placement, "h*0.82")

        parts.append(
            f"drawtext=text='{text}':fontsize=40:fontcolor=white:x=(w-text_w)/2:y={y}"
            f":enable='between(t,{ts},{ts+dur})':box=1:boxcolor=black@0.4:boxborderw=8"
        )

    return ",".join(parts) if parts else ""
