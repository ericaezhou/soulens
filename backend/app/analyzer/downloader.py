import os
import uuid
import tempfile
import subprocess
import httpx
import yt_dlp
from pathlib import Path


RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "instagram-reels-downloader-api.p.rapidapi.com"


def _rapidapi_fetch(instagram_url: str) -> dict | None:
    """Fetch reel metadata + direct video URL via RapidAPI. Returns data dict or None."""
    if not RAPIDAPI_KEY:
        return None
    try:
        resp = httpx.get(
            f"https://{RAPIDAPI_HOST}/download",
            params={"url": instagram_url},
            headers={"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": RAPIDAPI_HOST},
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("success") and body.get("data", {}).get("video_url"):
            return body["data"]
    except Exception:
        pass
    return None


def _cookies_file() -> str | None:
    """Write a Netscape cookies.txt from INSTAGRAM_SESSION_ID. Returns temp path or None."""
    session_id = os.getenv("INSTAGRAM_SESSION_ID", "")
    if not session_id:
        return None
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    f.write("# Netscape HTTP Cookie File\n")
    f.write(f".instagram.com\tTRUE\t/\tTRUE\t2147483647\tsessionid\t{session_id}\n")
    f.close()
    return f.name


def download_reel(url: str, output_dir: Path) -> dict:
    video_id = str(uuid.uuid4())
    final_path = output_dir / f"{video_id}.mp4"

    # --- Strategy 1: RapidAPI (no IP/rate-limit issues) ---
    rapi = _rapidapi_fetch(url)
    if rapi:
        try:
            with httpx.stream("GET", rapi["video_url"], timeout=60, follow_redirects=True) as r:
                r.raise_for_status()
                with open(final_path, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=1024 * 64):
                        f.write(chunk)
            meta = _probe_meta(str(final_path))
            return {
                "path": str(final_path),
                "video_id": video_id,
                "duration": rapi.get("duration") or meta.get("duration"),
                "title": rapi.get("title", ""),
                "uploader": rapi.get("author", ""),
                "view_count": rapi.get("view_count"),
                "like_count": rapi.get("like_count"),
                "upload_date": None,
                "description": rapi.get("title", ""),  # caption is in title field
                "width": meta.get("width"),
                "height": meta.get("height"),
                "fps": meta.get("fps"),
            }
        except Exception:
            pass  # fall through to yt-dlp

    # --- Strategy 2: yt-dlp with session cookie ---
    cookies_path = _cookies_file()
    raw_path = output_dir / f"{video_id}_raw.mp4"

    ydl_opts = {
        "outtmpl": str(output_dir / f"{video_id}_raw.%(ext)s"),
        "format": "best[height<=360]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 20,
        "retries": 1,
        **({"cookiefile": cookies_path} if cookies_path else {}),
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    if cookies_path:
        Path(cookies_path).unlink(missing_ok=True)

    downloaded = next(
        (f for f in output_dir.iterdir() if f.stem == f"{video_id}_raw"),
        None,
    )
    if not downloaded or not downloaded.exists():
        raise FileNotFoundError(f"Downloaded file not found for {video_id}")

    # Re-encode to H264 only if needed (OpenCV requires H264)
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(downloaded)],
        capture_output=True, text=True, timeout=30,
    )
    if probe.stdout.strip() != "h264":
        subprocess.run(
            ["ffmpeg", "-i", str(downloaded),
             "-vf", "scale=-2:360",
             "-c:v", "libx264", "-preset", "ultrafast",
             "-crf", "30", "-c:a", "aac", "-b:a", "64k", "-y", str(final_path)],
            check=True, capture_output=True, timeout=120,
        )
        downloaded.unlink(missing_ok=True)
    else:
        downloaded.rename(final_path)

    return {
        "path": str(final_path),
        "video_id": video_id,
        "duration": info.get("duration"),
        "title": info.get("title", ""),
        "uploader": info.get("uploader", ""),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "upload_date": info.get("upload_date"),
        "description": info.get("description", ""),
        "width": info.get("width"),
        "height": info.get("height"),
        "fps": info.get("fps"),
    }


def _probe_meta(path: str) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return {}
    import json
    data = json.loads(result.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    fps_str = video.get("r_frame_rate", "30/1")
    try:
        n, d = fps_str.split("/")
        fps = float(n) / float(d)
    except Exception:
        fps = 30.0
    return {
        "duration": float(data.get("format", {}).get("duration", 0)),
        "width": int(video.get("width", 0)),
        "height": int(video.get("height", 0)),
        "fps": fps,
    }
