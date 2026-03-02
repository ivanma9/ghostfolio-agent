"""Auth endpoints — login with Ghostfolio token or continue as guest."""
import httpx
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ghostfolio_agent.auth.db import AuthDB
from ghostfolio_agent.auth.jwt import create_token
from ghostfolio_agent.config import get_settings

logger = structlog.get_logger()

router = APIRouter()

_auth_db: AuthDB | None = None


async def _get_auth_db() -> AuthDB:
    global _auth_db
    if _auth_db is None:
        settings = get_settings()
        _auth_db = AuthDB("data/agent.db", settings.encryption_key)
        await _auth_db.init()
    return _auth_db


async def _validate_ghostfolio_token(token: str) -> bool:
    """Validate a Ghostfolio token — supports both security tokens and Bearer JWTs.

    Security tokens are short strings exchanged via POST /auth/anonymous.
    Bearer JWTs (start with 'eyJ') are used directly as Authorization headers.
    """
    settings = get_settings()
    base_url = settings.ghostfolio_base_url
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # First, try using it as a Bearer JWT (test against a known-working endpoint)
            resp = await client.get(
                f"{base_url}/api/v1/portfolio/holdings",
                headers={"Authorization": f"Bearer {token}"},
            )
            logger.info(
                "ghostfolio_bearer_check",
                status=resp.status_code,
                base_url=base_url,
            )
            if resp.status_code == 200:
                return True

            # If that fails, try exchanging as a security token
            resp = await client.post(
                f"{base_url}/api/v1/auth/anonymous",
                json={"accessToken": token},
            )
            logger.info(
                "ghostfolio_security_token_check",
                status=resp.status_code,
            )
            return resp.status_code == 201
    except Exception as e:
        logger.warning("ghostfolio_token_validation_failed", error=str(e), base_url=base_url)
        return False


class LoginRequest(BaseModel):
    ghostfolio_token: str


@router.post("/api/auth/login")
async def login(request: LoginRequest):
    """Validate Ghostfolio token, create/find user, return JWT."""
    is_valid = await _validate_ghostfolio_token(request.ghostfolio_token)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid Ghostfolio token")

    settings = get_settings()
    db = await _get_auth_db()

    # Determine role
    role = "admin" if request.ghostfolio_token == settings.ghostfolio_access_token else "user"

    # Find existing user or create new one
    existing = await db.find_user_by_token(request.ghostfolio_token)
    if existing:
        await db.update_last_login(existing["id"])
        user = existing
        user["role"] = role
    else:
        user = await db.create_user(ghostfolio_token=request.ghostfolio_token, role=role)

    jwt = create_token(user["id"], user["role"], settings.jwt_secret)
    return {"token": jwt, "role": user["role"], "user_id": user["id"]}


@router.post("/api/auth/guest")
async def guest_login():
    """Create ephemeral guest user and return JWT."""
    settings = get_settings()
    db = await _get_auth_db()
    user = await db.create_user(ghostfolio_token=None, role="guest")
    jwt = create_token(user["id"], user["role"], settings.jwt_secret)
    return {"token": jwt, "role": user["role"], "user_id": user["id"]}
