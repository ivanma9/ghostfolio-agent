"""JWT token creation and verification."""
import time
import jwt


def create_token(
    user_id: str, role: str, secret: str, expires_in: int = 86400
) -> str:
    """Create a signed JWT. expires_in is seconds (default 24h)."""
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": int(time.time()) + expires_in,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_token(token: str, secret: str) -> dict:
    """Verify and decode a JWT. Raises ValueError on any failure."""
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise ValueError(f"Invalid token: {e}") from e
