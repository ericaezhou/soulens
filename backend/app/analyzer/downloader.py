import uuid
import subprocess
import yt_dlp
from pathlib import Path


def download_reel(url: str, output_dir: Path) -> dict:
    video_id = str(uuid.uuid4())
    final_path = output_dir / f"{video_id}.mp4"

    ydl_opts = {
        "outtmpl": str(output_dir / f"{video_id}_raw.%(ext)s"),
        # Single combined stream — no merging, no format enumeration overhead
        "format": "best[height<=480]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

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
        capture_output=True, text=True,
    )
    if probe.stdout.strip() != "h264":
        subprocess.run(
            ["ffmpeg", "-i", str(downloaded),
             "-vf", "scale=-2:480",
             "-c:v", "libx264", "-preset", "ultrafast",
             "-crf", "28", "-c:a", "aac", "-b:a", "128k", "-y", str(final_path)],
            check=True, capture_output=True,
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
