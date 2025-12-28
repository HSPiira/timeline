"""Credential encryption utilities"""
import base64
import json

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from core.config import get_settings

settings = get_settings()


class CredentialEncryptor:
    """Encrypt/decrypt email credentials using Fernet symmetric encryption"""

    def __init__(self):
        # In production, use settings.secret_key or dedicated encryption key
        # For now, derive from secret_key
        self._fernet = Fernet(self._get_encryption_key())

    def _get_encryption_key(self) -> bytes:
        """
        Get encryption key derived from app secret_key using PBKDF2.

        Uses PBKDF2-HMAC-SHA256 with 100,000 iterations to derive a 32-byte key
        from the secret_key and deployment-specific salt, then base64url-encodes
        it for Fernet compatibility.

        This provides protection against brute-force attacks through:
        - Salt: Prevents rainbow table attacks
        - Iterations: Makes each derivation computationally expensive
        """
        # Derive 32-byte key using PBKDF2-HMAC-SHA256
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=settings.encryption_salt.encode(),
            iterations=100_000,
        )

        key_material = settings.secret_key.encode()
        derived_key = kdf.derive(key_material)

        # Fernet requires base64url-encoded 32-byte key
        return base64.urlsafe_b64encode(derived_key)

    def encrypt(self, credentials: dict) -> str:
        """
        Encrypt credentials dictionary to string.

        Args:
            credentials: Dictionary containing provider credentials

        Returns:
            Encrypted string safe for database storage
        """
        json_str = json.dumps(credentials)
        encrypted_bytes = self._fernet.encrypt(json_str.encode())
        return encrypted_bytes.decode()

    def decrypt(self, encrypted_str: str) -> dict:
        """
        Decrypt credentials string to dictionary.

        Args:
            encrypted_str: Encrypted credentials from database

        Returns:
            Decrypted credentials dictionary
        """
        try:
            decrypted_bytes = self._fernet.decrypt(encrypted_str.encode())
            json_str = decrypted_bytes.decode()
            result = json.loads(json_str)
            if not isinstance(result, dict):
                raise ValueError("Decrypted credentials must be a dictionary")
            return result
        except InvalidToken as e:
            raise ValueError(
                "Failed to decrypt credentials - invalid or corrupted data"
            ) from e
        except json.JSONDecodeError as e:
            raise ValueError("Decrypted credentials are not valid JSON") from e
