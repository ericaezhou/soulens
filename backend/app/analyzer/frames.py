"""Shared frame extraction utility used by cataloger and precision_trim."""
import base64
import subprocess


def grab_frame(clip_path: str, t: float) -> str | None:
    """Extract a single JPEG frame at time t, return as base64. Returns None on failure."""
    cmd = [
        "ffmpeg", "-ss", f"{t:.2f}", "-i", clip_path,
        "-frames:v", "1", "-vf", "scale=360:-2",
        "-f", "image2", "-vcodec", "mjpeg", "pipe:1",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        if result.returncode == 0 and result.stdout:
            return base64.b64encode(result.stdout).decode()
    except Exception:
        pass
    return None
