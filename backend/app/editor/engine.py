import subprocess
import json
import uuid
import os
import numpy as np
from pathlib import Path


def apply_style(footage_path: str, fingerprint: dict, output_dir: Path) -> dict:
    recipe = fingerprint.get("edit_recipe", {})
    color = fingerprint.get("color", {})
    audio = fingerprint.get("audio", {})

    output_path = output_dir / f"edit_{uuid.uuid4()}.mp4"

    # Probe footage
    probe = _probe_video(footage_path)
    if not probe:
        raise ValueError("Cannot read footage file")

    duration = probe["duration"]
    fps = probe["fps"]

    # Generate cut points
    avg_cut = recipe.get("target_cut_duration", 2.0)
    variation = recipe.get("cut_variation", 0.3)
    beat_times = audio.get("beat_times", []) if recipe.get("beat_sync") else []
    target_duration = min(duration, 30)  # Cap at 30s for Reels

    cuts = _generate_cuts(duration, target_duration, avg_cut, variation, beat_times)

    # Build color grade filter
    eq = recipe.get("color", {})
    color_filter = _build_color_filter(eq)

    # Build FFmpeg command
    cmd = _build_ffmpeg_cmd(footage_path, str(output_path), cuts, color_filter)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {result.stderr[-500:]}")

    file_size = output_path.stat().st_size if output_path.exists() else 0

    return {
        "output_path": str(output_path),
        "output_filename": output_path.name,
        "duration": target_duration,
        "cuts_applied": len(cuts),
        "grade_style": recipe.get("grade_style", "natural_balanced"),
        "file_size_bytes": file_size,
    }


def _probe_video(path: str) -> dict | None:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None

    data = json.loads(result.stdout)
    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video_stream:
        return None

    duration = float(data.get("format", {}).get("duration", 0))
    fps_str = video_stream.get("r_frame_rate", "30/1")
    try:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    except Exception:
        fps = 30.0

    return {
        "duration": duration,
        "fps": fps,
        "width": int(video_stream.get("width", 1080)),
        "height": int(video_stream.get("height", 1920)),
    }


def _generate_cuts(
    total_duration: float,
    target_duration: float,
    avg_cut: float,
    variation: float,
    beat_times: list[float],
) -> list[dict]:
    cuts = []
    t = 0
    rng = np.random.default_rng(42)

    while t < total_duration - 0.5 and sum(c["duration"] for c in cuts) < target_duration:
        # Vary cut length organically
        spread = avg_cut * variation
        cut_len = float(np.clip(rng.normal(avg_cut, spread), 0.4, avg_cut * 2.5))
        end = min(t + cut_len, total_duration)

        # Snap end to nearest beat if beat sync enabled
        if beat_times:
            nearest = min(beat_times, key=lambda b: abs(b - end))
            if abs(nearest - end) < 0.35 and nearest < total_duration:
                end = nearest

        cuts.append({"start": round(t, 3), "end": round(end, 3), "duration": round(end - t, 3)})
        t = end

    return cuts


def _build_color_filter(eq: dict) -> str:
    brightness = eq.get("brightness", 0)
    contrast = eq.get("contrast", 1.0)
    saturation = eq.get("saturation", 1.0)
    r_gain = eq.get("r_gain", 1.0)
    b_gain = eq.get("b_gain", 1.0)

    # Clamp to safe ranges
    brightness = max(-0.5, min(0.5, brightness))
    contrast = max(0.5, min(3.0, contrast))
    saturation = max(0.0, min(3.0, saturation))
    r_gain = max(0.5, min(2.0, r_gain))
    b_gain = max(0.5, min(2.0, b_gain))

    parts = [
        f"eq=brightness={brightness:.3f}:contrast={contrast:.3f}:saturation={saturation:.3f}",
    ]

    # Only apply channel mixer if there's meaningful warmth adjustment
    if abs(r_gain - 1.0) > 0.02 or abs(b_gain - 1.0) > 0.02:
        parts.append(f"colorchannelmixer=rr={r_gain:.3f}:bb={b_gain:.3f}")

    return ",".join(parts)


def _build_ffmpeg_cmd(
    input_path: str,
    output_path: str,
    cuts: list[dict],
    color_filter: str,
) -> list[str]:
    if not cuts:
        return [
            "ffmpeg", "-i", input_path,
            "-vf", color_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            output_path, "-y"
        ]

    n = len(cuts)
    filter_parts = []

    for i, cut in enumerate(cuts):
        start = cut["start"]
        dur = cut["duration"]
        filter_parts.append(
            f"[0:v]trim=start={start:.3f}:duration={dur:.3f},"
            f"setpts=PTS-STARTPTS,{color_filter}[v{i}];"
            f"[0:a]atrim=start={start:.3f}:duration={dur:.3f},"
            f"asetpts=PTS-STARTPTS[a{i}];"
        )

    v_streams = "".join(f"[v{i}]" for i in range(n))
    a_streams = "".join(f"[a{i}]" for i in range(n))
    filter_complex = (
        "".join(filter_parts)
        + f"{v_streams}concat=n={n}:v=1:a=0[outv];"
        + f"{a_streams}concat=n={n}:v=0:a=1[outa]"
    )

    return [
        "ffmpeg", "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        output_path, "-y"
    ]
