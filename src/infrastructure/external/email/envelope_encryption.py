"""Envelope encryption for OAuth credentials using KMS-like pattern"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any, cast

from cryptography.fernet import Fernet

from src.infrastructure.config.settings import get_settings
from src.shared.telemetry.logging import get_logger
from src.shared.utils import utc_now

logger = get_logger(__name__)


class EnvelopeEncryptor:
    """
    Envelope encryption for sensitive OAuth credentials.

    Architecture:
        1. Master Key (MEK): Derived from ENCRYPTION_SALT, never stored in DB
        2. Data Encryption Keys (DEK): Generated per credential, encrypted with MEK
        3. Encrypted Data: Actual credential encrypted with DEK

    Format: {key_id}:{encrypted_dek}:{encrypted_data}:{signature}

    This prevents full credential compromise from a single DB breach.
    Even with database access, attacker needs the master key.
    """

    def __init__(self):
        self.settings = get_settings()
        self._master_key = self._derive_master_key()

    def _derive_master_key(self) -> bytes:
        """
        Derive master encryption key from ENCRYPTION_SALT.

        In production, this should use AWS KMS, Google Cloud KMS, or HashiCorp Vault.
        For dev/testing, we derive from ENCRYPTION_SALT.
        """
        # Use PBKDF2 to derive a strong key from the salt
        salt_bytes = self.settings.encryption_salt.encode()
        key = hashlib.pbkdf2_hmac(
            "sha256",
            salt_bytes,
            b"timeline_oauth_master_key",  # Static salt for master key
            100000,  # Iterations
        )
        return base64.urlsafe_b64encode(key)

    def _generate_dek(self) -> bytes:
        """Generate a new data encryption key (32 bytes)"""
        return Fernet.generate_key()

    def _encrypt_dek(self, dek: bytes) -> bytes:
        """Encrypt DEK with master key"""
        fernet = Fernet(self._master_key)
        return fernet.encrypt(dek)

    def _decrypt_dek(self, encrypted_dek: bytes) -> bytes:
        """Decrypt DEK with master key"""
        fernet = Fernet(self._master_key)
        return fernet.decrypt(encrypted_dek)

    def _generate_key_id(self) -> str:
        """Generate unique key identifier"""
        timestamp = utc_now().strftime("%Y%m%d%H%M%S")
        random_part = secrets.token_hex(8)
        return f"dek_{timestamp}_{random_part}"

    def _sign_payload(self, payload: str) -> str:
        """Generate HMAC signature of payload"""
        signature = hmac.new(self._master_key, payload.encode(), hashlib.sha256).hexdigest()
        return signature

    def _verify_signature(self, payload: str, signature: str) -> bool:
        """Verify HMAC signature"""
        expected = self._sign_payload(payload)
        return hmac.compare_digest(expected, signature)

    def encrypt(self, data: str | dict[str, Any]) -> str:
        """
        Encrypt data using envelope encryption.

        Args:
            data: Data to encrypt (string or dict, will be JSON serialized)

        Returns:
            Encrypted envelope: {key_id}:{encrypted_dek}:{encrypted_data}:{signature}
        """
        try:
            # Convert to string if dict
            if isinstance(data, dict):
                data_str = json.dumps(data)
            else:
                data_str = str(data)

            # Generate new DEK for this data
            dek = self._generate_dek()
            key_id = self._generate_key_id()

            # Encrypt data with DEK
            fernet_dek = Fernet(dek)
            encrypted_data = fernet_dek.encrypt(data_str.encode())

            # Encrypt DEK with master key
            encrypted_dek = self._encrypt_dek(dek)

            # Encode for storage
            encrypted_dek_b64 = base64.urlsafe_b64encode(encrypted_dek).decode()
            encrypted_data_b64 = base64.urlsafe_b64encode(encrypted_data).decode()

            # Build envelope
            envelope = f"{key_id}:{encrypted_dek_b64}:{encrypted_data_b64}"

            # Sign envelope
            signature = self._sign_payload(envelope)

            # Final format
            final = f"{envelope}:{signature}"

            logger.debug(f"Encrypted data with key_id: {key_id}")
            return final

        except Exception as e:
            logger.error(f"Encryption failed: {e}", exc_info=True)
            raise ValueError(f"Encryption failed: {e}") from e

    def decrypt(self, encrypted_envelope: str) -> str | dict[str, Any]:
        """
        Decrypt data from envelope.

        Args:
            encrypted_envelope: Encrypted envelope string

        Returns:
            Decrypted data (as dict if JSON, otherwise string)

        Raises:
            ValueError: If decryption fails or signature invalid
        """
        try:
            # Parse envelope
            parts = encrypted_envelope.split(":")
            if len(parts) != 4:
                raise ValueError("Invalid envelope format")

            key_id, encrypted_dek_b64, encrypted_data_b64, signature = parts

            # Verify signature
            envelope = f"{key_id}:{encrypted_dek_b64}:{encrypted_data_b64}"
            if not self._verify_signature(envelope, signature):
                raise ValueError("Invalid signature - data may be tampered")

            # Decode
            encrypted_dek = base64.urlsafe_b64decode(encrypted_dek_b64)
            encrypted_data = base64.urlsafe_b64decode(encrypted_data_b64)

            # Decrypt DEK
            dek = self._decrypt_dek(encrypted_dek)

            # Decrypt data
            fernet_dek = Fernet(dek)
            data_bytes = fernet_dek.decrypt(encrypted_data)
            data_str = data_bytes.decode()

            # Try to parse as JSON
            try:
                result = json.loads(data_str)
                if isinstance(result, dict):
                    return cast(dict[str, Any], result)
                return data_str
            except json.JSONDecodeError:
                return data_str

        except Exception as e:
            logger.error(f"Decryption failed: {e}", exc_info=True)
            raise ValueError(f"Decryption failed: {e}") from e

    def rotate_key(self, encrypted_envelope: str) -> str:
        """
        Rotate data encryption key (DEK).

        Decrypts data and re-encrypts with a new DEK.
        Note: This does not rotate the master encryption key (MEK).
        MEK rotation requires external KMS integration.

        Args:
            encrypted_envelope: Data encrypted with old key

        Returns:
            Data encrypted with new DEK
        """
        # Decrypt with old key
        data = self.decrypt(encrypted_envelope)

        # Encrypt with new key (generates new DEK)
        return self.encrypt(data)

    def extract_key_id(self, encrypted_envelope: str) -> str:
        """Extract key ID from encrypted envelope without decrypting"""
        parts = encrypted_envelope.split(":")
        if len(parts) != 4:
            raise ValueError("Invalid envelope format")
        return parts[0]


class OAuthStateManager:
    """
    Manager for OAuth state parameters with signing and expiration.

    State format: {state_id}:{signature}
    Actual state data stored in database, signature prevents tampering.
    """

    def __init__(self):
        self.settings = get_settings()
        self._signing_key = self.settings.secret_key.encode()

    def create_signed_state(self, state_id: str) -> str:
        """
        Create signed state parameter.

        Args:
            state_id: State record ID (CUID)

        Returns:
            Signed state: {state_id}:{signature}
        """
        signature = hmac.new(self._signing_key, state_id.encode(), hashlib.sha256).hexdigest()
        return f"{state_id}:{signature}"

    def verify_and_extract(self, signed_state: str) -> str:
        """
        Verify signature and extract state ID.

        Args:
            signed_state: Signed state from callback

        Returns:
            State ID if valid

        Raises:
            ValueError: If signature invalid
        """
        parts = signed_state.split(":")
        if len(parts) != 2:
            raise ValueError("Invalid state format")

        state_id, signature = parts

        # Verify signature
        expected = hmac.new(self._signing_key, state_id.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid state signature - possible CSRF attack")

        return state_id
