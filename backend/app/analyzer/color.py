import cv2
import numpy as np
from sklearn.cluster import KMeans


def analyze_color_grade(video_path: str, scenes: list[dict]) -> dict:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return _empty_color()

    frame_samples = []
    sample_times = []

    # Sample mid-frame of each scene, plus start/end for short scenes
    for scene in scenes[:30]:
        mid = (scene["start_time"] + scene["end_time"]) / 2
        sample_times.append(mid)
        if scene["duration"] > 2:
            sample_times.append(scene["start_time"] + 0.2)

    # Ensure we sample at least 10 frames even if few scenes
    if len(sample_times) < 10:
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)
        sample_times = [total * i / 12 for i in range(1, 12)]

    for t in sorted(set(sample_times))[:40]:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ret, frame = cap.read()
        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_samples.append(frame_rgb)

    cap.release()

    if not frame_samples:
        return _empty_color()

    # Per-channel stats
    all_pixels = np.vstack([f.reshape(-1, 3).astype(np.float32) / 255.0 for f in frame_samples])

    avg_rgb = all_pixels.mean(axis=0)
    std_rgb = all_pixels.std(axis=0)

    # HSV analysis
    hsv_frames = [cv2.cvtColor(f, cv2.COLOR_RGB2HSV).astype(np.float32) for f in frame_samples]
    avg_hue = float(np.mean([f[:, :, 0].mean() for f in hsv_frames])) / 180.0
    avg_sat = float(np.mean([f[:, :, 1].mean() for f in hsv_frames])) / 255.0
    avg_val = float(np.mean([f[:, :, 2].mean() for f in hsv_frames])) / 255.0

    # Luminance
    gray_frames = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0 for f in frame_samples]
    avg_brightness = float(np.mean([g.mean() for g in gray_frames]))
    avg_contrast = float(np.mean([g.std() for g in gray_frames]))

    # Shadow/highlight split toning
    dark_pixels = all_pixels[all_pixels.mean(axis=1) < 0.25]
    bright_pixels = all_pixels[all_pixels.mean(axis=1) > 0.75]
    shadow_cast = _color_cast(dark_pixels) if len(dark_pixels) > 100 else "neutral"
    highlight_cast = _color_cast(bright_pixels) if len(bright_pixels) > 100 else "neutral"

    # Warmth (R-B balance)
    warmth = float(avg_rgb[0] - avg_rgb[2])

    # Color grade classification
    grade_style = _classify_grade(avg_sat, avg_brightness, avg_contrast, warmth)

    # Dominant palette via K-means
    palette = _extract_palette(frame_samples[len(frame_samples) // 2])

    # Skin tone detection (important for portrait/lifestyle content)
    skin_ratio = _detect_skin_ratio(frame_samples)

    # FFmpeg-compatible eq params for replication
    eq_params = _compute_eq_params(avg_brightness, avg_contrast, avg_sat, warmth)

    return {
        "avg_rgb": [round(float(v), 3) for v in avg_rgb],
        "saturation": round(avg_sat, 3),
        "brightness": round(avg_brightness, 3),
        "contrast": round(avg_contrast, 3),
        "warmth": round(warmth, 3),
        "hue_shift": round(avg_hue, 3),
        "shadow_cast": shadow_cast,
        "highlight_cast": highlight_cast,
        "grade_style": grade_style,
        "dominant_palette": palette,
        "skin_ratio": round(skin_ratio, 3),
        "eq_params": eq_params,
    }


def _color_cast(pixels: np.ndarray) -> str:
    if len(pixels) == 0:
        return "neutral"
    mean = pixels.mean(axis=0)
    r, g, b = mean[0], mean[1], mean[2]
    if r > g and r > b and r > 0.4:
        return "warm_red"
    elif b > r and b > g and b > 0.4:
        return "cool_blue"
    elif g > r and g > b and g > 0.4:
        return "green_teal"
    elif r > 0.45 and g > 0.4 and b < 0.35:
        return "golden_orange"
    return "neutral"


def _classify_grade(sat: float, bright: float, contrast: float, warmth: float) -> str:
    if sat > 0.55 and warmth > 0.05:
        return "vibrant_warm"
    elif sat > 0.55 and warmth < -0.05:
        return "vibrant_cool"
    elif sat < 0.25:
        return "desaturated_moody"
    elif sat < 0.35 and contrast > 0.22:
        return "faded_film"
    elif bright > 0.68:
        return "bright_airy"
    elif bright < 0.30:
        return "dark_moody"
    elif contrast > 0.24:
        return "high_contrast_punchy"
    elif warmth > 0.08:
        return "golden_warm"
    elif warmth < -0.06:
        return "cool_teal"
    else:
        return "natural_balanced"


def _extract_palette(frame: np.ndarray, n_colors: int = 6) -> list[str]:
    try:
        pixels = frame.reshape(-1, 3).astype(np.float32)
        # Subsample for speed
        idx = np.random.choice(len(pixels), min(2000, len(pixels)), replace=False)
        sample = pixels[idx]

        kmeans = KMeans(n_clusters=n_colors, random_state=42, n_init=5, max_iter=100)
        kmeans.fit(sample)

        colors = kmeans.cluster_centers_.astype(int)
        # Sort by luminance (darkest to brightest)
        lum = [0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] for c in colors]
        sorted_colors = [colors[i] for i in np.argsort(lum)]

        return [f"#{int(r):02x}{int(g):02x}{int(b):02x}" for r, g, b in sorted_colors]
    except Exception:
        return ["#1a1a1a", "#666666", "#cccccc"]


def _detect_skin_ratio(frames: list[np.ndarray]) -> float:
    ratios = []
    for frame in frames[:10]:
        hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
        # Skin tone range in HSV
        lower = np.array([0, 20, 70])
        upper = np.array([25, 170, 255])
        mask = cv2.inRange(hsv, lower, upper)
        ratio = mask.sum() / 255 / (frame.shape[0] * frame.shape[1])
        ratios.append(ratio)
    return float(np.mean(ratios)) if ratios else 0


def _compute_eq_params(brightness: float, contrast: float, saturation: float, warmth: float) -> dict:
    # FFmpeg eq filter params
    eq_brightness = round((brightness - 0.5) * 0.6, 3)
    eq_contrast = round(1.0 + contrast * 1.5, 3)
    eq_saturation = round(saturation / 0.45, 3)  # Normalize to 1.0 = standard
    r_gain = round(1.0 + max(0, warmth) * 0.4, 3)
    b_gain = round(1.0 + max(0, -warmth) * 0.4, 3)

    return {
        "brightness": eq_brightness,
        "contrast": eq_contrast,
        "saturation": eq_saturation,
        "r_gain": r_gain,
        "b_gain": b_gain,
    }


def _empty_color() -> dict:
    return {
        "avg_rgb": [0.5, 0.5, 0.5],
        "saturation": 0.5,
        "brightness": 0.5,
        "contrast": 0.15,
        "warmth": 0.0,
        "hue_shift": 0.5,
        "shadow_cast": "neutral",
        "highlight_cast": "neutral",
        "grade_style": "unknown",
        "dominant_palette": [],
        "skin_ratio": 0,
        "eq_params": {"brightness": 0, "contrast": 1, "saturation": 1, "r_gain": 1, "b_gain": 1},
    }
