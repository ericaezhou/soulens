"""
Executes an edit plan produced by Claude against raw footage.
Outputs: MP4 + FCPXml process file.
"""
import subprocess
import json
import uuid
import numpy as np
from pathlib import Path



def apply_style(
    footage_path: str,
    style_profile: dict,
    output_dir: Path,
    candidate_clips: list[dict] | None = None,
    apply_color: bool = True,
) -> dict:
    recipe = style_profile.get("edit_recipe", {})

    output_stem = f"edit_{uuid.uuid4()}"
    mp4_path = output_dir / f"{output_stem}.mp4"

    probe = _probe_video(footage_path)
    if not probe:
        raise ValueError("Cannot read footage file")

    duration = probe["duration"]

    if candidate_clips is None:
        cuts = []
    elif candidate_clips:
        cuts = _clips_to_cuts(candidate_clips, recipe)
    else:
        cuts = _generate_cuts(
            total_duration=duration,
            target_duration=recipe.get("target_duration_s", 25.0),
            avg_cut=recipe.get("target_cut_duration", 2.0),
            variation=recipe.get("cut_variation", 0.3),
            beat_sync_strength=recipe.get("beat_sync_strength", 0.5),
            hook_duration=recipe.get("hook_duration_s", 3.0),
        )

    color = recipe.get("color", {})
    color_filter = _build_color_filter(color) if apply_color else None

    cmd = _build_ffmpeg_cmd(footage_path, str(mp4_path), cuts, color_filter)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {result.stderr[-800:]}")

    return {
        "mp4_path": str(mp4_path),
        "mp4_filename": mp4_path.name,
        "cuts_applied": len(cuts),
        "output_duration_s": round(sum(c["duration"] for c in cuts), 2),
        "grade_style": recipe.get("grade_style", "natural_balanced") if apply_color else "none",
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

    for clip in candidate_clips:
        remaining = target_duration - accumulated
        if remaining <= 0.2:
            break

        start = clip["start_time"]
        clip_dur = max(0.2, min(clip["duration"], remaining))
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
    color_filter: str | None,
) -> list[str]:
    vf = f",{color_filter}" if color_filter else ""

    if not cuts:
        base = ["ffmpeg", "-i", input_path]
        if color_filter:
            base += ["-vf", color_filter]
        else:
            base += ["-c:v", "copy"]
        return base + ["-c:a", "aac", "-b:a", "192k", output_path, "-y"]

    n = len(cuts)
    filter_parts = []
    for i, cut in enumerate(cuts):
        s, dur = cut["start"], cut["duration"]
        filter_parts.append(
            f"[0:v]trim=start={s:.3f}:duration={dur:.3f},setpts=PTS-STARTPTS{vf}[v{i}];"
            f"[0:a]atrim=start={s:.3f}:duration={dur:.3f},asetpts=PTS-STARTPTS[a{i}];"
        )

    v_in = "".join(f"[v{i}]" for i in range(n))
    a_in = "".join(f"[a{i}]" for i in range(n))
    filter_complex = (
        "".join(filter_parts)
        + f"{v_in}concat=n={n}:v=1:a=0[outv];"
        + f"{a_in}concat=n={n}:v=0:a=1[outa]"
    )

    return [
        "ffmpeg", "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k",
        output_path, "-y",
    ]


