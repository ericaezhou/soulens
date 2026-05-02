"""
Pulls 20 latest reels from an Instagram profile and builds a Style Profile
by analyzing all of them and synthesizing patterns across them.
"""
import json
import re
import asyncio
from pathlib import Path
from typing import Callable

import instaloader

from app.analyzer.downloader import download_reel
from app.analyzer.video import detect_scenes, analyze_pacing, analyze_motion
from app.analyzer.audio import analyze_audio
from app.analyzer.color import analyze_color_grade
from app.analyzer.text import detect_text_overlays
from app.config import PROFILES_DIR, INSTAGRAM_SESSION_ID


def extract_username(instagram_url: str) -> str:
    """Extract username from a URL, @handle, or plain username."""
    url = instagram_url.strip().rstrip("/")
    # Plain username or @username
    if not url.startswith("http"):
        username = url.lstrip("@").lower()
        if re.match(r"^[a-zA-Z0-9._]{1,30}$", username):
            return username
    # Full URL
    match = re.search(r"instagram\.com/([^/?#]+)", url)
    if match:
        username = match.group(1).lower()
        for segment in ("reels", "posts", "stories", "p", "reel"):
            if username == segment:
                raise ValueError("That looks like a post URL, not a profile. Use a username or instagram.com/username")
        return username
    raise ValueError(f"Could not parse username from: {instagram_url}")


def _get_loader() -> instaloader.Instaloader:
    if not INSTAGRAM_SESSION_ID:
        raise ValueError("INSTAGRAM_SESSION_ID is not set in .env")
    L = instaloader.Instaloader(
        max_connection_attempts=3,
        request_timeout=15,
        quiet=True,
    )
    L.context._session.cookies.set("sessionid", INSTAGRAM_SESSION_ID, domain=".instagram.com")
    # Headers that make requests look like Instagram web app, reducing 403s
    L.context._session.headers.update({
        "X-IG-App-ID": "936619743392459",
        "X-ASBD-ID": "198387",
        "X-IG-WWW-Claim": "0",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    })
    L.context.username = "autoedittt"
    return L


def fetch_reel_urls(username: str, count: int = 20) -> list[str]:
    """Use instaloader to list the latest `count` reel URLs from a profile."""
    L = _get_loader()
    profile = instaloader.Profile.from_username(L.context, username)

    urls = []
    for post in profile.get_posts():
        if post.is_video:
            urls.append(f"https://www.instagram.com/p/{post.shortcode}/")
        if len(urls) >= count:
            break

    if not urls:
        raise ValueError(f"No reels found for @{username}. Make sure the profile is public.")

    return urls


def analyze_single_reel(reel_url: str, reel_dir: Path) -> dict | None:
    """Download and fully analyze one reel. Returns None if download fails."""
    try:
        meta = download_reel(reel_url, reel_dir)
        path = meta["path"]
        duration = meta.get("duration") or 30

        scenes = detect_scenes(path)
        pacing = analyze_pacing(scenes, duration)
        audio = analyze_audio(path)
        color = analyze_color_grade(path, scenes)
        text = detect_text_overlays(path)
        motion = analyze_motion(path, scenes)

        # Delete video file immediately — we only need the analysis data
        Path(path).unlink(missing_ok=True)

        # Beat sync ratio
        beat_times = audio.get("beat_times", [])
        cut_times = [s["start_time"] for s in scenes[1:]]
        synced = sum(
            1 for cut in cut_times
            if any(abs(cut - b) < 0.25 for b in beat_times)
        )
        beat_sync_ratio = synced / len(cut_times) if cut_times else 0.0

        return {
            "url": reel_url,
            "meta": meta,
            "pacing": pacing,
            "audio": audio,
            "color": color,
            "text": text,
            "motion": motion,
            "beat_sync_ratio": round(beat_sync_ratio, 3),
            "scenes": scenes[:30],
        }
    except Exception as e:
        return {"url": reel_url, "error": str(e)}


def build_profile(
    username: str,
    reel_urls: list[str],
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict:
    """
    Analyze all reels and return a raw profile dict (pre-Claude synthesis).
    on_progress(completed, total, reel_url) called after each reel.
    """
    user_dir = PROFILES_DIR / username / "reels"
    user_dir.mkdir(parents=True, exist_ok=True)

    reels_data = []
    for i, url in enumerate(reel_urls):
        result = analyze_single_reel(url, user_dir)
        reels_data.append(result)
        if on_progress:
            on_progress(i + 1, len(reel_urls), url)

    successful = [r for r in reels_data if "error" not in r]
    if not successful:
        raise ValueError("All reel downloads failed. Profile may be private or rate-limited.")

    return {
        "username": username,
        "reels_analyzed": len(successful),
        "reels_failed": len(reels_data) - len(successful),
        "reels": reels_data,
    }


def save_profile(username: str, profile: dict) -> Path:
    path = PROFILES_DIR / username / "profile.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2))
    return path


def load_profile(username: str) -> dict | None:
    path = PROFILES_DIR / username / "profile.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
