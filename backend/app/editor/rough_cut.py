"""
Pass 1: Universal rough cut — style-agnostic quality filter.
Pure OpenCV/numpy — $0, no API calls.

Window-based analysis (0.5s blocks):
- Per window: MAX optical flow (catches any shaky frame in the block),
  median Laplacian blur, mean brightness
- Reject bad windows, absorb short bad gaps (≤ 1s) between good runs,
  merge consecutive good windows into candidate clips ≥ 1.5s
"""
import cv2
import numpy as np
import subprocess
import json

WINDOW_S = 0.5           # score in 0.5-second blocks
MIN_CLIP_S = 1.5         # drop good segments shorter than this
GAP_FILL_WINDOWS = 2     # absorb up to 2 consecutive bad windows (~1s) sandwiched between good footage

THRESHOLDS = {
    "min_blur": 40.0,           # median Laplacian variance per window — below = blurry
    "min_brightness": 15.0,     # mean pixel value — below = too dark
    "max_brightness": 240.0,    # above = overexposed
    "max_motion": 15.0,         # hard ceiling — always flag above this
    "min_motion_flag": 8.0,     # never flag below this (prevents false positives on tripod footage)
    "motion_relative_factor": 2.5,  # also flag if max_motion > factor × video median
}


def run_rough_cut(video_path: str, scenes: list[dict] | None = None) -> dict:
    """
    Analyse every frame in 0.5s windows.
    Window max-motion catches shakiness even when only a few frames within it spike.
    `scenes` accepted for API compatibility but ignored.
    """
    duration = _probe_duration(video_path)
    if duration <= 0:
        return _empty_result()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_scores = _score_all_frames(cap, fps)
    cap.release()

    if not frame_scores:
        return _empty_result()

    windows = _score_windows(frame_scores, fps)
    _apply_thresholds(windows)
    candidates, rejected_windows = _build_clips(windows, duration)

    raw_dur = round(duration, 2)
    cand_dur = round(sum(c["duration"] for c in candidates), 2)

    return {
        "total_scenes": len(windows),
        "candidate_count": len(candidates),
        "rejected_count": len(rejected_windows),
        "raw_duration_s": raw_dur,
        "candidate_duration_s": cand_dur,
        "retention_pct": round(cand_dur / raw_dur * 100) if raw_dur > 0 else 0,
        "rejection_summary": _summarize_rejections(rejected_windows),
        "candidates": candidates,
        "rejected": rejected_windows,
    }


def _score_all_frames(cap: cv2.VideoCapture, fps: float) -> list[dict]:
    """Read every frame, compute blur + brightness + motion (optical flow)."""
    scores = []
    prev_gray = None
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Downsample for speed — analysis at 360p is plenty
        small = cv2.resize(gray, (360, 202))

        blur = float(cv2.Laplacian(small, cv2.CV_64F).var())
        brightness = float(small.mean())

        motion = 0.0
        if prev_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, small, None, 0.5, 3, 15, 3, 5, 1.2, 0
            )
            motion = float(np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2).mean())

        scores.append({
            "frame": frame_idx,
            "time": round(frame_idx / fps, 4),
            "blur": blur,
            "brightness": brightness,
            "motion": motion,
        })

        prev_gray = small
        frame_idx += 1

    return scores


def _score_windows(frame_scores: list[dict], fps: float) -> list[dict]:
    """
    Group frames into WINDOW_S-second blocks, compute metrics only.
    Thresholding is done separately in _apply_thresholds so the motion
    threshold can be set adaptively based on the video's own baseline.
    Use MAX motion — a single shaky frame should fail the whole window.
    Use MEDIAN blur — robust to single-frame focus glitches.
    """
    window_size = max(1, round(fps * WINDOW_S))
    windows = []

    for start in range(0, len(frame_scores), window_size):
        chunk = frame_scores[start:start + window_size]
        if not chunk:
            continue

        t_start = chunk[0]["time"]
        t_end = chunk[-1]["time"] + (1.0 / fps)

        windows.append({
            "start_time": round(t_start, 3),
            "end_time": round(t_end, 3),
            "duration": round(t_end - t_start, 3),
            "blur_score": round(float(np.median([f["blur"] for f in chunk])), 1),
            "brightness": round(float(np.mean([f["brightness"] for f in chunk])), 1),
            "motion_std": round(float(max(f["motion"] for f in chunk)), 2),
            "reject_reasons": [],
            "keep": True,
        })

    return windows


def _apply_thresholds(windows: list[dict]) -> None:
    """
    Set keep/reject_reasons on each window using an adaptive motion threshold.

    Adaptive motion threshold = min(hard_ceiling, max(min_flag, median × factor))
    - Still video (median=2): threshold = min(15, max(8, 5)) = 8  → catches subtle end-shakiness
    - Handheld (median=5):    threshold = min(15, max(8, 12.5)) = 12.5
    - Generally shaky (median=10): threshold = min(15, max(8, 25)) = 15  → caps at hard ceiling
    """
    if not windows:
        return

    median_motion = float(np.median([w["motion_std"] for w in windows]))
    adaptive_max = min(
        THRESHOLDS["max_motion"],
        max(THRESHOLDS["min_motion_flag"], median_motion * THRESHOLDS["motion_relative_factor"]),
    )

    for w in windows:
        reasons = []
        if w["blur_score"] < THRESHOLDS["min_blur"]:       reasons.append("blurry")
        if w["brightness"] < THRESHOLDS["min_brightness"]: reasons.append("too_dark")
        if w["brightness"] > THRESHOLDS["max_brightness"]: reasons.append("overexposed")
        if w["motion_std"] > adaptive_max:                  reasons.append("shaky")
        w["reject_reasons"] = reasons
        w["keep"] = len(reasons) == 0


def _build_clips(windows: list[dict], duration: float) -> tuple[list[dict], list[dict]]:
    """
    Merge consecutive good windows into clips.
    Short bad gaps (≤ GAP_FILL_WINDOWS) sandwiched between good runs are absorbed.
    """
    if not windows:
        return [], []

    n = len(windows)
    filled = [w["keep"] for w in windows]

    # Gap fill: if a short bad run has good footage on both sides, absorb it
    i = 0
    while i < n:
        if not filled[i]:
            j = i
            while j < n and not filled[j]:
                j += 1
            run_len = j - i
            has_good_before = any(filled[:i])
            has_good_after = any(filled[j:])
            if run_len <= GAP_FILL_WINDOWS and has_good_before and has_good_after:
                for k in range(i, j):
                    filled[k] = True
            i = j
        else:
            i += 1

    candidates = []
    rejected_windows = []
    i = 0
    while i < n:
        state = filled[i]
        j = i
        while j < n and filled[j] == state:
            j += 1

        chunk = windows[i:j]
        t_start = chunk[0]["start_time"]
        t_end = min(chunk[-1]["end_time"], duration)
        seg_dur = round(t_end - t_start, 3)

        seg_blur = round(float(np.mean([w["blur_score"] for w in chunk])), 1)
        seg_bright = round(float(np.mean([w["brightness"] for w in chunk])), 1)
        seg_motion = round(float(np.max([w["motion_std"] for w in chunk])), 2)

        reasons = []
        if not state:
            seen: dict[str, bool] = {}
            for w in chunk:
                for r in w["reject_reasons"]:
                    seen[r] = True
            reasons = list(seen.keys()) or ["bad_frames"]

        entry = {
            "start_time": round(t_start, 3),
            "end_time": round(t_end, 3),
            "duration": seg_dur,
            "blur_score": seg_blur,
            "brightness": seg_bright,
            "motion_std": seg_motion,
            "reject_reasons": reasons,
            "keep": state and seg_dur >= MIN_CLIP_S,
        }

        if state and seg_dur >= MIN_CLIP_S:
            candidates.append(entry)
        elif not state:
            rejected_windows.append(entry)

        i = j

    return candidates, rejected_windows


def _probe_duration(video_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return float(json.loads(result.stdout).get("format", {}).get("duration", 0))
    return 0.0


def _summarize_rejections(rejected: list[dict]) -> dict:
    summary: dict[str, int] = {}
    for r in rejected:
        for reason in r["reject_reasons"]:
            summary[reason] = summary.get(reason, 0) + 1
    return summary


def _empty_result() -> dict:
    return {
        "total_scenes": 0, "candidate_count": 0, "rejected_count": 0,
        "raw_duration_s": 0, "candidate_duration_s": 0, "retention_pct": 0,
        "rejection_summary": {}, "candidates": [], "rejected": [],
    }
