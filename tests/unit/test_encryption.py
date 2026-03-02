"""Tests for Ghostfolio token encryption/decryption."""
import pytest
from cryptography.fernet import Fernet


def _generate_key() -> str:
    return Fernet.generate_key().decode()


class TestEncryption:
    def test_round_trip(self):
        from ghostfolio_agent.auth.encryption import encrypt_token, decrypt_token
        key = _generate_key()
        plaintext = "my-ghostfolio-token-abc123"
        encrypted = encrypt_token(plaintext, key)
        assert encrypted != plaintext.encode()
        decrypted = decrypt_token(encrypted, key)
        assert decrypted == plaintext

    def test_different_keys_fail(self):
        from ghostfolio_agent.auth.encryption import encrypt_token, decrypt_token
        key1 = _generate_key()
        key2 = _generate_key()
        encrypted = encrypt_token("secret", key1)
        with pytest.raises(Exception):
            decrypt_token(encrypted, key2)

    def test_empty_token(self):
        from ghostfolio_agent.auth.encryption import encrypt_token, decrypt_token
        key = _generate_key()
        encrypted = encrypt_token("", key)
        assert decrypt_token(encrypted, key) == ""
