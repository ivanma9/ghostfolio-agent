"""FastAPI auth dependency — extracts and validates user from JWT."""
from fastapi import HTTPException

from ghostfolio_agent.auth.jwt import verify_token
from ghostfolio_agent.auth.db import AuthDB


async def get_current_user(
    authorization: str | None,
    jwt_secret: str,
    auth_db: AuthDB,
) -> dict:
    """Extract user from Authorization header. Raises 401 on failure.

    This is a building block — chat.py will wrap it in a FastAPI Depends()
    that injects jwt_secret and auth_db from app state.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = verify_token(token, jwt_secret)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await auth_db.get_user(payload["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
