"""
Global Phase 1 cache — keyed by clip file fingerprint + candidate timestamps.

Cache key: SHA-256 of (file_size + first 1MB of file + candidate segment timestamps).
Hashing the full video would be too slow; size + first 1MB is a reliable fingerprint
for any file that hasn't been re-encoded or trimmed.

Cached value: list of {scene_id, shot_type, energy, description} — the Claude output only.
Frames (_frame_b64) are NOT cached — they're fast to re-grab and are job-specific paths.
"""
import hashlib
import json
from pathlib import Path

from app.config import PHASE1_CACHE_DIR


def get_clip_cache_key(clip_path: str, candidates: list[dict]) -> str:
    h = hashlib.sha256()
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
