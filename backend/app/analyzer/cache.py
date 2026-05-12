"""
Global Phase 1 cache — keyed by clip file fingerprint + candidate timestamps + schema version.

Cache key: SHA-256 of (SCHEMA_VERSION + file_size + first 1MB of file + candidate timestamps).
Hashing the full video would be too slow; size + first 1MB is a reliable fingerprint
for any file that hasn't been re-encoded or trimmed.

Bump SCHEMA_VERSION whenever the Phase 1 output schema or model changes. Old entries stay
on disk but are never matched by the new key — effectively abandoned without a manual delete.

Cached value: list of Phase 1 scene dicts — Claude output only.
Frames (_frame_b64) are NOT cached — they're fast to re-grab and are job-specific paths.
"""
import hashlib
import json
from pathlib import Path

from app.config import PHASE1_CACHE_DIR

# Bump whenever Phase 1 schema or model changes to invalidate old entries automatically.
SCHEMA_VERSION = "v2"


def get_clip_cache_key(clip_path: str, candidates: list[dict]) -> str:
    h = hashlib.sha256()
    h.update(SCHEMA_VERSION.encode())

    path = Path(clip_path)
    h.update(str(path.stat().st_size).encode())
    with open(path, "rb") as f:
        h.update(f.read(1024 * 1024))  # first 1MB

    # Include candidate timestamps — rough cut is deterministic per file,
    # but this makes the key exact in case thresholds ever change.
    cand_sig = json.dumps(
        [{"s": c["start_time"], "e": c["end_time"]} for c in candidates],
        separators=(",", ":"),
    )
    h.update(cand_sig.encode())
    return h.hexdigest()


def load_phase1_cache(key: str) -> list[dict] | None:
    path = PHASE1_CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def save_phase1_cache(key: str, descriptions: list[dict]) -> None:
    try:
        (PHASE1_CACHE_DIR / f"{key}.json").write_text(json.dumps(descriptions))
    except Exception:
        pass
