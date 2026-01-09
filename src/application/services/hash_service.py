"""
Hash service for computing cryptographic hashes.

Follows OCP - closed for modification, open for extension.
New hash algorithms can be added without modifying this class.
"""

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class HashAlgorithm(ABC):
    """Abstract base class for hash algorithms (OCP)"""

    @abstractmethod
    def hash(self, data: str) -> str:
        """Compute hash of the input data"""
        pass


class SHA256Algorithm(HashAlgorithm):
    """SHA-256 hash algorithm implementation"""

    def hash(self, data: str) -> str:
        return hashlib.sha256(data.encode()).hexdigest()


class SHA512Algorithm(HashAlgorithm):
    """SHA-512 hash algorithm implementation"""

    def hash(self, data: str) -> str:
        return hashlib.sha512(data.encode()).hexdigest()


class HashService:
    """
    Hash service following OCP - closed for modification, open for extension.
    New hash algorithms can be added without modifying this class.

    This is the single source of truth for event hash computation.
    Used by both event creation and verification to ensure consistency.
    """

    def __init__(self, algorithm: HashAlgorithm | None = None):
        self.algorithm = algorithm or SHA256Algorithm()

    @staticmethod
    def canonical_json(data: dict[str, Any]) -> str:
        """Convert a dictionary to a canonical JSON string"""
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    def compute_hash(
        self,
        subject_id: str,
        event_type: str,
        schema_version: int,
        event_time: datetime,
        payload: dict[str, Any],
        previous_hash: str | None,
    ) -> str:
        """
        Compute cryptographic hash for event integrity.

        Hash includes:
        - subject_id: Who the event is about
        - event_type: What happened
        - schema_version: Schema used
        - event_time: When it happened (ISO format)
        - payload: Event data (canonicalized JSON)
        - previous_hash: Link to previous event (creates chain)

        Returns:
            SHA-256 hex digest of the canonical JSON representation
        """
        hash_content = {
            "subject_id": subject_id,
            "event_type": event_type,
            "schema_version": schema_version,
            "event_time": event_time.isoformat(),
            "payload": payload,
            "previous_hash": previous_hash,
        }
        return self.algorithm.hash(self.canonical_json(hash_content))
