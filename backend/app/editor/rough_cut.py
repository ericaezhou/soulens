"""
Pass 1: Universal rough cut — style-agnostic quality filter.
Pure OpenCV/numpy — no API cost. Runs on every scene in raw footage.

Detects and rejects: blurry, too dark, overexposed, shaky, too short, duplicates.
Returns candidate clips (passed quality checks) for Pass 2 (style-based selection).
"""
import cv2
import numpy as np


THRESHOLDS = {
    "min_duration_s": 0.8,       # shorter clips are likely mistakes or cuts
    "min_blur": 60.0,             # Laplacian variance — below = blurry/out of focus
    "min_brightness": 20.0,       # mean pixel value — below = too dark
    "max_brightness": 235.0,      # above = overexposed/blown out
    "max_motion_std": 12.0,       # optical flow std — above = camera shake
    "duplicate_corr": 0.97,       # histogram correlation — above = near-duplicate scene
}


def run_rough_cut(video_path: str, scenes: list[dict]) -> dict:
    """
    Score all scenes for technical quality and return candidates + rejected.
    """
    if not scenes:
        return _empty_result()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    scored = []
    for scene in scenes:
        result = _score_scene(cap, scene)
        scored.append(result)

    cap.release()

    _flag_duplicates(scored, video_path)

    candidates = [s for s in scored if s["keep"]]
    rejected = [s for s in scored if not s["keep"]]

    return {
        "total_scenes": len(scored),
        "candidate_count": len(candidates),
        "rejected_count": len(rejected),
        "raw_duration_s": round(sum(s["duration"] for s in scored), 2),
        "candidate_duration_s": round(sum(s["duration"] for s in candidates), 2),
        "retention_pct": round(len(candidates) / len(scored) * 100) if scored else 0,
        "rejection_summary": _summarize_rejections(rejected),
        "candidates": candidates,
        "rejected": rejected,
    }


def _score_scene(cap: cv2.VideoCapture, scene: dict) -> dict:
    start, end, duration = scene["start_time"], scene["end_time"], scene["duration"]

    # Duration check — skip frame reads for obviously short clips
    if duration < THRESHOLDS["min_duration_s"]:
        return _make_result(scene, reasons=["too_short"])

    # Sample 3 frames evenly across the scene
    frames_gray = []
    blur_scores, brightness_scores = [], []

    for t_frac in (0.25, 0.5, 0.75):
        cap.set(cv2.CAP_PROP_POS_MSEC, (start + duration * t_frac) * 1000)
        ret, frame = cap.read()
        if not ret:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frames_gray.append(gray)
        blur_scores.append(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness_scores.append(float(gray.mean()))

    if not frames_gray:
        return _make_result(scene, reasons=["unreadable"])

    avg_blur = float(np.mean(blur_scores))
    avg_brightness = float(np.mean(brightness_scores))

    # Motion stability: optical flow std between consecutive sampled frames
    motion_std = 0.0
    if len(frames_gray) >= 2:
        stds = []
        for i in range(len(frames_gray) - 1):
            flow = cv2.calcOpticalFlowFarneback(
                frames_gray[i], frames_gray[i + 1],
                None, 0.5, 3, 15, 3, 5, 1.2, 0,
            )
            stds.append(float(flow.std()))
        motion_std = float(np.mean(stds))

    reasons = []
    if avg_blur < THRESHOLDS["min_blur"]:
        reasons.append("blurry")
    if avg_brightness < THRESHOLDS["min_brightness"]:
        reasons.append("too_dark")
    elif avg_brightness > THRESHOLDS["max_brightness"]:
        reasons.append("overexposed")
    if motion_std > THRESHOLDS["max_motion_std"]:
        reasons.append("shaky")

    return _make_result(
        scene,
        blur_score=round(avg_blur, 1),
        brightness=round(avg_brightness, 1),
        motion_std=round(motion_std, 2),
        reasons=reasons,
    )


def _flag_duplicates(scored: list[dict], video_path: str):
    """Compare mid-frame histograms of adjacent passing scenes and flag near-duplicates."""
    cap = cv2.VideoCapture(video_path)
    prev_hist = None
    prev_scene = None

    for scene in scored:
        if not scene["keep"]:
            prev_hist = None
            prev_scene = None
            continue

        mid = (scene["start_time"] + scene["end_time"]) / 2
        cap.set(cv2.CAP_PROP_POS_MSEC, mid * 1000)
        ret, frame = cap.read()
        if not ret:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
        cv2.normalize(hist, hist)

        if prev_hist is not None:
            corr = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
            if corr > THRESHOLDS["duplicate_corr"]:
                scene["keep"] = False
                scene["reject_reasons"].append("duplicate")
                prev_hist = None
                prev_scene = None
                continue

        prev_hist = hist
        prev_scene = scene

    cap.release()


def _summarize_rejections(rejected: list[dict]) -> dict:
    summary: dict[str, int] = {}
    for r in rejected:
        for reason in r["reject_reasons"]:
            summary[reason] = summary.get(reason, 0) + 1
    return summary


def _make_result(
    scene: dict,
    blur_score: float = 0.0,
    brightness: float = 0.0,
    motion_std: float = 0.0,
    reasons: list[str] | None = None,
) -> dict:
    reasons = reasons or []
    return {
        "start_time": scene["start_time"],
        "end_time": scene["end_time"],
        "duration": scene["duration"],
        "blur_score": blur_score,
        "brightness": brightness,
        "motion_std": motion_std,
        "reject_reasons": reasons,
        "keep": len(reasons) == 0,
    }


def _empty_result() -> dict:
    return {
        "total_scenes": 0,
        "candidate_count": 0,
        "rejected_count": 0,
        "raw_duration_s": 0,
        "candidate_duration_s": 0,
        "retention_pct": 0,
        "rejection_summary": {},
        "candidates": [],
        "rejected": [],
    }
