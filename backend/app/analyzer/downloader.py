import yt_dlp
import uuid
import os
from pathlib import Path


def download_reel(url: str, output_dir: Path) -> dict:
    video_id = str(uuid.uuid4())
    output_template = str(output_dir / f"{video_id}.%(ext)s")
    final_path = output_dir / f"{video_id}.mp4"

    ydl_opts = {
        "outtmpl": output_template,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegVideoConvertor",
            "preferedformat": "mp4",
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # Find the downloaded file (might have different extension before conversion)
    downloaded = None
    for f in output_dir.iterdir():
        if f.stem == video_id:
            downloaded = f
            break

    if downloaded and downloaded.suffix != ".mp4":
        downloaded.rename(final_path)
        downloaded = final_path
    elif downloaded:
        final_path = downloaded

    if not downloaded or not downloaded.exists():
        raise FileNotFoundError(f"Downloaded file not found for job {video_id}")

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
