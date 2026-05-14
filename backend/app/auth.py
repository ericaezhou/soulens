"""
JWT verification for Supabase Auth tokens.
Apply `Depends(require_auth)` to any endpoint that costs money to call.
"""
import os
import jwt
from fastapi import HTTPException, Header


def require_auth(authorization: str = Header(None)) -> dict:
    """
    FastAPI dependency — extracts and verifies the Supabase JWT.
    Returns the decoded payload (includes sub = user_id, email, etc.).
    Raises 401 if missing or invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.split(" ", 1)[1]
    secret = os.getenv("SUPABASE_JWT_SECRET", "")
    if not secret:
        raise HTTPException(status_code=500, detail="Auth not configured")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
