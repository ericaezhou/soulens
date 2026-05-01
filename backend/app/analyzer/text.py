import cv2
import numpy as np
import pytesseract
from PIL import Image


def detect_text_overlays(video_path: str) -> dict:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return _empty_text()

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0

    # Sample every ~1.5 seconds
    step = max(1, int(fps * 1.5))
    detections = []
    placements = []

    frame_num = 0
    while frame_num < total_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if not ret:
            break

        timestamp = frame_num / fps if fps > 0 else 0
        h, w = frame.shape[:2]

        # Preprocess for better OCR on overlay text
        result = _extract_text_from_frame(frame)

        if result["has_text"]:
            result["timestamp"] = round(timestamp, 2)
            detections.append(result)

            # Track placement
            if result.get("placement"):
                placements.append(result["placement"])

        frame_num += step

    cap.release()

    if not detections:
        return {"has_text": False, "text_count": 0, "text_frequency": 0,
                "dominant_placement": None, "text_timing": "none",
                "sample_texts": [], "style_hints": []}

    text_frequency = len(detections) / duration if duration > 0 else 0

    # Dominant placement
    placement_counts: dict[str, int] = {}
    for p in placements:
        placement_counts[p] = placement_counts.get(p, 0) + 1
    dominant_placement = max(placement_counts, key=placement_counts.get) if placement_counts else "center"

    # Text timing pattern
    timestamps = [d["timestamp"] for d in detections]
    text_timing = _classify_text_timing(timestamps, duration)

    # Style hints from font analysis
    style_hints = _infer_text_style(detections)

    return {
        "has_text": True,
        "text_count": len(detections),
        "text_frequency": round(text_frequency, 3),
        "dominant_placement": dominant_placement,
        "text_timing": text_timing,
        "sample_texts": [d.get("text", "") for d in detections[:5]],
        "style_hints": style_hints,
    }


def _extract_text_from_frame(frame: np.ndarray) -> dict:
    h, w = frame.shape[:2]

    # Try multiple preprocessing approaches for overlay text detection
    results = []

    # 1. Full frame
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    text_full = pytesseract.image_to_string(gray, config="--psm 6 --oem 3").strip()
    if text_full:
        results.append(text_full)

    # 2. Check regions (top third, bottom third, center) where text typically appears
    regions = {
        "top": frame[:h // 3, :],
        "bottom": frame[2 * h // 3:, :],
        "center": frame[h // 3: 2 * h // 3, :],
    }

    found_in = []
    for region_name, region in regions.items():
        g = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        # Threshold to pop text
        _, thresh = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text = pytesseract.image_to_string(thresh, config="--psm 6 --oem 3").strip()
        if len(text) > 2:
            found_in.append(region_name)

    all_text = " ".join(results).strip()

    if not all_text and not found_in:
        return {"has_text": False}

    # Determine dominant placement
    placement = None
    if found_in:
        if "bottom" in found_in:
            placement = "lower_third"
        elif "top" in found_in:
            placement = "upper_third"
        elif "center" in found_in:
            placement = "center"

    return {
        "has_text": bool(all_text or found_in),
        "text": all_text[:200],  # Cap length
        "placement": placement,
    }


def _classify_text_timing(timestamps: list[float], duration: float) -> str:
    if not timestamps or duration == 0:
        return "none"

    first_text = timestamps[0]
    first_ratio = first_text / duration

    coverage = len(timestamps) / (duration / 1.5)  # Approximate frames with text

    if first_ratio < 0.1 and coverage > 0.5:
        return "throughout_with_hook"
    elif first_ratio < 0.1:
        return "early_hook"
    elif coverage > 0.7:
        return "throughout"
    elif coverage < 0.2:
        return "sparse"
    else:
        return "periodic"


def _infer_text_style(detections: list[dict]) -> list[str]:
    hints = []
    texts = [d.get("text", "") for d in detections if d.get("text")]

    if not texts:
        return hints

    # Check for all-caps (bold/impactful style)
    caps_count = sum(1 for t in texts if t == t.upper() and t.strip())
    if caps_count / len(texts) > 0.5:
        hints.append("all_caps_bold")

    # Check for short punchy text
    avg_len = np.mean([len(t.split()) for t in texts if t.strip()])
    if avg_len < 4:
        hints.append("short_punchy")
    elif avg_len > 10:
        hints.append("long_descriptive")

    placements = [d.get("placement") for d in detections if d.get("placement")]
    if placements:
        from collections import Counter
        top_placement = Counter(placements).most_common(1)[0][0]
        hints.append(f"placement_{top_placement}")

    return hints


def _empty_text() -> dict:
    return {
        "has_text": False,
        "text_count": 0,
        "text_frequency": 0,
        "dominant_placement": None,
        "text_timing": "none",
        "sample_texts": [],
        "style_hints": [],
    }
