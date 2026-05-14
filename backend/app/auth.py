"""
Auth via Supabase client — works regardless of JWT algorithm (HS256 or RS256).
Apply `Depends(require_auth)` to any endpoint that costs money to call.
"""
from fastapi import HTTPException, Header
from app.storage import _get_client


def require_auth(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.split(" ", 1)[1]
    try:
        client = _get_client()
        response = client.auth.get_user(token)
        if not response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"sub": response.user.id, "email": response.user.email}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth error: {e}")
