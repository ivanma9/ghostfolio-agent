"""AES encryption for Ghostfolio tokens at rest using Fernet."""
from cryptography.fernet import Fernet


def encrypt_token(plaintext: str, key: str) -> bytes:
    """Encrypt a Ghostfolio access token. Key must be a valid Fernet key."""
    f = Fernet(key.encode())
    return f.encrypt(plaintext.encode())


def decrypt_token(ciphertext: bytes, key: str) -> str:
    """Decrypt a Ghostfolio access token."""
    f = Fernet(key.encode())
    return f.decrypt(ciphertext).decode()
