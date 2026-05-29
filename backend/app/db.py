"""
Supabase profile store — persistent storage backed by creator_profiles table.
Schema: (id, user_id, slug, display_name, reel_urls JSONB, profile_data JSONB,
         status, reels_analyzed, created_at, updated_at)
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _sb():
    from app.storage import _get_client
    client = _get_client()
    if client is None:
        raise RuntimeError("Supabase not configured — set SUPABASE_URL and SUPABASE_SERVICE_KEY")
    return client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_profile(user_id: str, slug: str, display_name: str, reel_urls: list[str], status: str = "processing") -> None:
    sb = _sb()
    existing = sb.table("creator_profiles").select("id").eq("user_id", user_id).eq("slug", slug).execute()
    if existing.data:
        sb.table("creator_profiles").update({
            "display_name": display_name,
            "reel_urls": reel_urls,
            "status": status,
            "updated_at": _now(),
        }).eq("user_id", user_id).eq("slug", slug).execute()
    else:
        try:
            sb.table("creator_profiles").insert({
                "user_id": user_id,
                "slug": slug,
                "display_name": display_name,
                "reel_urls": reel_urls,
                "status": status,
            }).execute()
        except Exception as e:
            if "Maximum limit" in str(e):
                raise ValueError("Maximum limit of 5 profiles reached for this user account.")
            raise


def update_status(user_id: str, slug: str, status: str, reels_analyzed: int | None = None) -> None:
    data: dict = {"status": status, "updated_at": _now()}
    if reels_analyzed is not None:
        data["reels_analyzed"] = reels_analyzed
    _sb().table("creator_profiles").update(data).eq("user_id", user_id).eq("slug", slug).execute()


def get_profile_record(user_id: str, slug: str) -> dict | None:
    resp = _sb().table("creator_profiles").select("*").eq("user_id", user_id).eq("slug", slug).execute()
    if not resp.data:
        return None
    return resp.data[0]


def list_profiles(user_id: str) -> list[dict]:
    resp = _sb().table("creator_profiles").select(
        "slug,display_name,reel_urls,status,reels_analyzed,created_at,updated_at"
    ).eq("user_id", user_id).order("updated_at", desc=True).execute()
    return resp.data or []


def delete_profile_record(user_id: str, slug: str) -> None:
    _sb().table("creator_profiles").delete().eq("user_id", user_id).eq("slug", slug).execute()


def save_profile_data(user_id: str, slug: str, profile_data: dict) -> None:
    _sb().table("creator_profiles").update({
        "profile_data": profile_data,
        "updated_at": _now(),
    }).eq("user_id", user_id).eq("slug", slug).execute()


def load_profile_data(user_id: str, slug: str) -> dict | None:
    resp = _sb().table("creator_profiles").select("profile_data").eq("user_id", user_id).eq("slug", slug).execute()
    if not resp.data:
        return None
    return resp.data[0].get("profile_data")
