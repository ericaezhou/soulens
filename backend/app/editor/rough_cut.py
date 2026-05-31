"""
Pass 1: Universal rough cut — style-agnostic quality filter.
Pure OpenCV/numpy — $0, no external calls.

For multi-clip sessions, call in three steps:
  1. score_clip(path)             → windows with metrics, no thresholding yet
  2. compute_global_threshold()   → median-of-per-clip-medians (robust to outlier clips)
  3. build_clip_candidates()      → apply threshold, return candidates + rejected

Single-clip shortcut: run_rough_cut() does all three internally.
"""
import math
import shutil
import tempfile
import cv2
import numpy as np
import subprocess
import json
from pathlib import Path

WINDOW_S = 0.5           # score in 0.5-second blocks
MIN_CLIP_S = 1.5         # drop good segments shorter than this
MAX_CANDIDATE_S = 5.0    # split candidates longer than this into equal sub-segments
GAP_FILL_WINDOWS = 2     # absorb up to 2 consecutive bad windows (~1s) sandwiched between good footage
FRAME_SAMPLE = 2         # analyze every Nth frame; optical flow normalized by N to keep same scale

THRESHOLDS = {
    "min_blur": 40.0,
    "min_brightness": 15.0,
    "max_brightness": 240.0,
    "max_brightness_std": 40.0,  # std dev of brightness within a window — high = flash/black frame
    "motion_ceiling": 15.0,      # cap on the computed global threshold
    "motion_floor": 8.0,         # floor on the computed global threshold
    "motion_relative_factor": 2.5,
}


# ─── Step 1: Score ────────────────────────────────────────────────────────────

def score_clip(video_path: str) -> tuple[list[dict], float]:
    """
    Read every frame, compute per-window metrics (blur, brightness, max motion).
    Returns (windows, duration). No thresholding — keep/reasons not set yet.
    Call compute_global_threshold() across all clips before thresholding.

    Copies the file to /tmp first so OpenCV reads from local container storage
    instead of network-attached storage, eliminating per-frame network latency.
    """
    duration = _probe_duration(video_path)
    if duration <= 0:
        return [], 0.0

    tmp_path = None
    try:
        suffix = Path(video_path).suffix or ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
        shutil.copy2(video_path, tmp_path)

        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            return [], 0.0

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_scores = _score_all_frames(cap, fps)
        cap.release()
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)

    if not frame_scores:
        return [], 0.0

    windows = _score_windows(frame_scores, fps)
    return windows, duration


# ─── Step 2: Global threshold ─────────────────────────────────────────────────

def compute_global_threshold(all_windows: list[list[dict]]) -> float:
    """
    Derive one motion threshold for the whole session using median-of-per-clip-medians.

    Why not a simple global median of all windows?
      A super-shaky clip contributes thousands of high-motion windows and inflates
      the global median, raising the bar for all normal clips.

    Median-of-medians fixes this: each clip gets one vote (its median), so
    one outlier clip out of N shifts the result by at most 1/N.

    Examples:
      12 calm clips (median ≈ 3) + 1 super-shaky clip (median ≈ 30):
        clip medians → [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 30]
        median-of-medians → 3  →  threshold = min(15, max(8, 7.5)) = 8
        shaky clip windows (motion 20–30) >> 8 → mostly rejected ✓

      All handheld clips (median ≈ 6):
        median-of-medians → 6  →  threshold = min(15, max(8, 15)) = 15

      All tripod clips (median ≈ 2):
        median-of-medians → 2  →  threshold = min(15, max(8, 5)) = 8
    """
    clip_medians = [
        float(np.median([w["motion_std"] for w in windows]))
        for windows in all_windows
        if windows
    ]
    if not clip_medians:
        return THRESHOLDS["max_motion"]

    global_median = float(np.median(clip_medians))
    return min(
        THRESHOLDS["motion_ceiling"],
        max(THRESHOLDS["motion_floor"], global_median * THRESHOLDS["motion_relative_factor"]),
    )


# ─── Step 3: Threshold + build candidates ────────────────────────────────────

def build_clip_candidates(
    windows: list[dict],
    duration: float,
    motion_threshold: float,
) -> tuple[list[dict], list[dict], dict]:
    """
    Apply thresholds and split windows into candidates + rejected.
    Returns (candidates, rejected_windows, summary_dict).

    Each candidate gets two extra fields:
      peak_motion_s — timestamp of the highest-motion window within that segment
                       (optical flow peak, passed downstream as a key_moment_s hint)
    Long candidates (> MAX_CANDIDATE_S) are split into equal sub-segments so that
    Phase 1 / Phase 3 always receive focused windows rather than sprawling clips.
    """
    _apply_thresholds(windows, motion_threshold)
    candidates, rejected = _build_clips(windows, duration)
    candidates = _split_long_candidates(candidates, windows)
    _add_peak_motion(candidates, windows)

    raw_dur = round(duration, 2)
    cand_dur = round(sum(c["duration"] for c in candidates), 2)

    summary = {
        "candidate_count": len(candidates),
        "rejected_count": len(rejected),
        "raw_duration_s": raw_dur,
        "candidate_duration_s": cand_dur,
        "retention_pct": round(cand_dur / raw_dur * 100) if raw_dur > 0 else 0,
        "rejection_summary": _summarize_rejections(rejected),
    }
    return candidates, rejected, summary


# ─── Single-clip shortcut ─────────────────────────────────────────────────────

def run_rough_cut(video_path: str, scenes: list[dict] | None = None) -> dict:
    """
    Single-clip shortcut: score + self-adaptive threshold + build candidates.
    For multi-clip sessions use score_clip / compute_global_threshold / build_clip_candidates.
    """
    windows, duration = score_clip(video_path)
    if not windows:
        return _empty_result()

    motion_threshold = compute_global_threshold([windows])
    candidates, rejected, summary = build_clip_candidates(windows, duration, motion_threshold)

    return {
        **summary,
        "total_scenes": len(windows),
        "candidates": candidates,
        "rejected": rejected,
    }


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _score_all_frames(cap: cv2.VideoCapture, fps: float) -> list[dict]:
    """
    Read every frame but only decode + analyze every FRAME_SAMPLE-th frame.
    Optical flow is divided by FRAME_SAMPLE so motion values stay in the same
    scale as single-frame analysis — thresholds don't need adjustment.
    """
    scores = []
    prev_gray = None
    frame_idx = 0

    while True:
        if frame_idx % FRAME_SAMPLE != 0:
            if not cap.grab():   # advance without decoding — much faster
                break
            frame_idx += 1
            continue

        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (360, 202))

        blur = float(cv2.Laplacian(small, cv2.CV_64F).var())
        brightness = float(small.mean())

        motion = 0.0
        if prev_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, small, None, 0.5, 3, 15, 3, 5, 1.2, 0
            )
            # Divide by FRAME_SAMPLE: flow spans N frame intervals, normalize to per-frame scale
            motion = float(np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2).mean()) / FRAME_SAMPLE

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
    """Group frames into WINDOW_S blocks. MAX motion, MEDIAN blur, MEAN brightness."""
    window_size = max(1, round(fps * WINDOW_S))
    windows = []

    for start in range(0, len(frame_scores), window_size):
        chunk = frame_scores[start:start + window_size]
        if not chunk:
            continue

        t_start = chunk[0]["time"]
        t_end = chunk[-1]["time"] + (1.0 / fps)

        brightnesses = [f["brightness"] for f in chunk]
        windows.append({
            "start_time": round(t_start, 3),
            "end_time": round(t_end, 3),
            "duration": round(t_end - t_start, 3),
            "blur_score": round(float(np.median([f["blur"] for f in chunk])), 1),
            "brightness": round(float(np.mean(brightnesses)), 1),
            "brightness_std": round(float(np.std(brightnesses)), 1),
            "motion_std": round(float(max(f["motion"] for f in chunk)), 2),
            "reject_reasons": [],
            "keep": True,
        })

    return windows


def _apply_thresholds(windows: list[dict], motion_threshold: float) -> None:
    for w in windows:
        reasons = []
        if w["blur_score"] < THRESHOLDS["min_blur"]:             reasons.append("blurry")
        if w["brightness"] < THRESHOLDS["min_brightness"]:       reasons.append("too_dark")
        if w["brightness"] > THRESHOLDS["max_brightness"]:       reasons.append("overexposed")
        if w["brightness_std"] > THRESHOLDS["max_brightness_std"]: reasons.append("flash")
        if w["motion_std"] > motion_threshold:                    reasons.append("shaky")
        w["reject_reasons"] = reasons
        w["keep"] = len(reasons) == 0


def _build_clips(windows: list[dict], duration: float) -> tuple[list[dict], list[dict]]:
    """Merge consecutive good windows; absorb short bad gaps between good runs."""
    if not windows:
        return [], []

    n = len(windows)
    filled = [w["keep"] for w in windows]

    i = 0
    while i < n:
        if not filled[i]:
            j = i
            while j < n and not filled[j]:
                j += 1
            if (j - i) <= GAP_FILL_WINDOWS and any(filled[:i]) and any(filled[j:]):
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

        reasons: list[str] = []
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


def _split_long_candidates(candidates: list[dict], windows: list[dict]) -> list[dict]:
    """Split any candidate longer than MAX_CANDIDATE_S into sub-segments.

    Split points are placed at the lowest-motion window near each target boundary
    (±1s search) so we avoid cutting mid-action. Falls back to exact time split
    if no windows are found in the search range.
    """
    result = []
    for c in candidates:
        if c["duration"] <= MAX_CANDIDATE_S:
            result.append(c)
            continue

        n = math.ceil(c["duration"] / MAX_CANDIDATE_S)
        target_dur = c["duration"] / n

        # Build split boundaries by finding quiet moments near each target split point
        boundaries = [c["start_time"]]
        for i in range(1, n):
            target_t = c["start_time"] + i * target_dur
            nearby = [
                w for w in windows
                if w["start_time"] >= target_t - 1.0
                and w["end_time"] <= target_t + 1.0
                and w["start_time"] >= c["start_time"]
                and w["end_time"] <= c["end_time"]
            ]
            if nearby:
                quietest = min(nearby, key=lambda w: w["motion_std"])
                boundaries.append(round(quietest["end_time"], 3))
            else:
                boundaries.append(round(target_t, 3))
        boundaries.append(c["end_time"])

        for i in range(len(boundaries) - 1):
            sub_start = boundaries[i]
            sub_end = boundaries[i + 1]
            dur = round(sub_end - sub_start, 3)
            if dur < MIN_CLIP_S:
                continue
            result.append({**c, "start_time": sub_start, "end_time": sub_end, "duration": dur})

    return result


def _add_peak_motion(candidates: list[dict], windows: list[dict]) -> None:
    """Add peak_motion_s to each candidate — the timestamp of its highest-motion window."""
    for c in candidates:
        in_range = [
            w for w in windows
            if w["start_time"] >= c["start_time"] - 0.01 and w["end_time"] <= c["end_time"] + 0.01
        ]
        if in_range:
            best = max(in_range, key=lambda w: w["motion_std"])
            c["peak_motion_s"] = round((best["start_time"] + best["end_time"]) / 2, 3)
        else:
            c["peak_motion_s"] = round((c["start_time"] + c["end_time"]) / 2, 3)


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
