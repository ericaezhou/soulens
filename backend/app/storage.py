"""
Supabase Storage helper — uploads final outputs (MP4, FCPXML, SRT) to the
`outputs` bucket and returns public URLs.

Gracefully returns None when SUPABASE_URL / SUPABASE_SERVICE_KEY are not set,
so local dev works without any Supabase configuration.
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return None
    from supabase import create_client
    _client = create_client(url, key)
    return _client


def upload_output(local_path: Path, job_id: str) -> str | None:
    """
    Upload a file to the `outputs` bucket under {job_id}/{filename}.
    Returns the public URL, or None if Supabase is not configured or upload fails.
    """
    client = _get_client()
    if client is None:
        return None

    object_path = f"{job_id}/{local_path.name}"
    try:
        with open(local_path, "rb") as f:
            data = f.read()
        client.storage.from_("outputs").upload(
            path=object_path,
            file=data,
            file_options={"content-type": _content_type(local_path), "upsert": "true"},
        )
        return client.storage.from_("outputs").get_public_url(object_path)
    except Exception as e:
        logger.warning("Supabase upload failed for %s: %s", local_path.name, e)
        return None


def _content_type(path: Path) -> str:
    return {
        ".mp4": "video/mp4",
        ".fcpxml": "application/xml",
        ".srt": "text/plain",
    }.get(path.suffix.lower(), "application/octet-stream")
