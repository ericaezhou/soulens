"""
SQLite profile store — local dev. Mirrors to Supabase when we scale.
Schema: profiles(slug, display_name, reel_urls JSON, status, reels_analyzed, created_at, updated_at)
"""
import json
import sqlite3
from pathlib import Path

_DB_PATH = Path("data/auto_edit.db")


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                slug         TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                reel_urls    TEXT NOT NULL DEFAULT '[]',
                status       TEXT NOT NULL DEFAULT 'processing',
                reels_analyzed INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        c.commit()
    _migrate_filesystem_profiles()


def _migrate_filesystem_profiles() -> None:
    """Import any profiles already on disk that aren't in the DB yet."""
    profiles_dir = Path("data/profiles")
    if not profiles_dir.exists():
        return

    for profile_dir in profiles_dir.iterdir():
        if not profile_dir.is_dir():
            continue
        slug = profile_dir.name
        if get_profile_record(slug):
            continue  # already in DB

        profile_json = profile_dir / "profile.json"
        if not profile_json.exists():
            continue

        try:
            data = json.loads(profile_json.read_text())
            synthesis = data.get("synthesis", {})
            status = "error" if "error" in synthesis else "completed"
            reels_analyzed = data.get("reels_analyzed", 0)

            # Recover reel URLs from the reel_cache directory
            reel_urls: list[str] = []
            cache_dir = profile_dir / "reel_cache"
            if cache_dir.exists():
                for cache_file in sorted(cache_dir.glob("*.json")):
                    try:
                        cached = json.loads(cache_file.read_text())
                        url = cached.get("url")
                        if url:
                            reel_urls.append(url)
                    except Exception:
                        continue

            display_name = slug.replace("_", " ").title()
            upsert_profile(slug, display_name, reel_urls, status)
            update_status(slug, status, reels_analyzed)
        except Exception:
            continue


def upsert_profile(slug: str, display_name: str, reel_urls: list[str], status: str = "processing") -> None:
    with _conn() as c:
        c.execute("""
            INSERT INTO profiles (slug, display_name, reel_urls, status, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(slug) DO UPDATE SET
                display_name   = excluded.display_name,
                reel_urls      = excluded.reel_urls,
                status         = excluded.status,
                updated_at     = datetime('now')
        """, (slug, display_name, json.dumps(reel_urls), status))
        c.commit()


def update_status(slug: str, status: str, reels_analyzed: int | None = None) -> None:
    with _conn() as c:
        if reels_analyzed is not None:
            c.execute(
                "UPDATE profiles SET status=?, reels_analyzed=?, updated_at=datetime('now') WHERE slug=?",
                (status, reels_analyzed, slug),
            )
        else:
            c.execute(
                "UPDATE profiles SET status=?, updated_at=datetime('now') WHERE slug=?",
                (status, slug),
            )
        c.commit()


def get_profile_record(slug: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM profiles WHERE slug=?", (slug,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["reel_urls"] = json.loads(d["reel_urls"])
        return d


def list_profiles() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM profiles ORDER BY updated_at DESC").fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["reel_urls"] = json.loads(d["reel_urls"])
            result.append(d)
        return result


def delete_profile_record(slug: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM profiles WHERE slug=?", (slug,))
        c.commit()
