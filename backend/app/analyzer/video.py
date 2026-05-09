import cv2
import base64
import subprocess
import numpy as np
from scenedetect import detect, ContentDetector, AdaptiveDetector


def detect_scenes(video_path: str) -> list[dict]:
    try:
        scene_list = detect(video_path, AdaptiveDetector())
    except Exception:
        scene_list = detect(video_path, ContentDetector(threshold=27.0))

    scenes = []
    for scene in scene_list:
        start = scene[0].get_seconds()
        end = scene[1].get_seconds()
        scenes.append({
            "start_time": round(start, 3),
            "end_time": round(end, 3),
            "duration": round(end - start, 3),
        })

    return scenes


def analyze_pacing(scenes: list[dict], total_duration: float) -> dict:
    if not scenes:
        return {
            "avg_cut_duration": total_duration,
            "cut_count": 0,
            "cuts_per_second": 0,
            "rhythm": "static",
            "cut_durations": [],
            "pacing_variation": 0,
        }

    durations = [s["duration"] for s in scenes]
    avg = float(np.mean(durations))
    std = float(np.std(durations))

    return {
        "avg_cut_duration": round(avg, 3),
        "cut_count": len(scenes),
        "cuts_per_second": round(len(scenes) / total_duration, 3) if total_duration > 0 else 0,
        "rhythm": _classify_rhythm(avg),
        "cut_durations": [round(d, 3) for d in durations],
        "pacing_variation": round(std / avg if avg > 0 else 0, 3),
        "fastest_cut": round(min(durations), 3),
        "slowest_cut": round(max(durations), 3),
    }


def _classify_rhythm(avg_duration: float) -> str:
    if avg_duration < 0.6:
        return "ultra_fast"
    elif avg_duration < 1.2:
        return "fast"
    elif avg_duration < 2.0:
        return "medium_fast"
    elif avg_duration < 3.5:
        return "medium"
    elif avg_duration < 6.0:
        return "slow"
    else:
        return "cinematic"


def analyze_motion(video_path: str, scenes: list[dict]) -> dict:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"avg_motion": 0, "motion_style": "unknown"}

    fps = cap.get(cv2.CAP_PROP_FPS)
    motion_scores = []
    prev_frame = None

    sample_times = []
    for scene in scenes[:20]:  # Sample up to 20 scenes
        mid = (scene["start_time"] + scene["end_time"]) / 2
        sample_times.extend([scene["start_time"] + 0.1, mid])

    for t in sample_times[:40]:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if not ret:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_frame is not None:
            diff = cv2.absdiff(gray, prev_frame)
            motion_scores.append(float(np.mean(diff)))
        prev_frame = gray

    cap.release()

    avg_motion = float(np.mean(motion_scores)) if motion_scores else 0
    return {
        "avg_motion": round(avg_motion, 2),
        "motion_style": _classify_motion(avg_motion),
    }


def extract_key_frames(video_path: str, duration: float, scenes: list[dict] | None = None) -> list[str]:
    """
    Extract 4 frames at scene boundaries for Claude vision analysis.
    Hook (first cut) + 2 evenly sampled body scenes + outro.
    Falls back to fixed timestamps if no scene data.
    Capped at 4 to keep synthesis API cost low (~$0.05 per profile).
    """
    if scenes and len(scenes) >= 3:
        starts = [s["start_time"] for s in scenes]
        hook_times = starts[:1]
        outro_time = starts[-1]
        body_starts = starts[1:-1]
        step = max(1, len(body_starts) // 2)
        body_times = body_starts[::step][:2]
        sample_times = hook_times + body_times + [outro_time]
    else:
        sample_times = [0.5, duration * 0.35, duration * 0.65, duration * 0.85]

    frames = []
    seen: set[float] = set()
    for t in sample_times:
        t = round(max(0.1, min(t, duration - 0.1)), 2)
        if t in seen:
            continue
        seen.add(t)
        cmd = [
            "ffmpeg", "-ss", f"{t:.2f}", "-i", video_path,
            "-frames:v", "1", "-vf", "scale=360:-2",
            "-f", "image2", "-vcodec", "mjpeg", "pipe:1",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            if result.returncode == 0 and result.stdout:
                frames.append(base64.b64encode(result.stdout).decode())
        except Exception:
            continue

    return frames


def _classify_motion(score: float) -> str:
    if score < 5:
        return "static_talking_head"
    elif score < 12:
        return "subtle_movement"
    elif score < 25:
        return "moderate_motion"
    elif score < 45:
        return "high_energy"
    else:
        return "extreme_action"
