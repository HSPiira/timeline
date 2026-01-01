"""
Hash service for computing cryptographic hashes.

Follows OCP - closed for modification, open for extension.
New hash algorithms can be added without modifying this class.
"""

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime


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
    """

    def __init__(self, algorithm: HashAlgorithm | None = None):
        self.algorithm = algorithm or SHA256Algorithm()

    @staticmethod
    def canonical_json(data: dict) -> str:
        """Convert a dictionary to a canonical JSON string"""
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    def compute_hash(
        self,
        tenant_id: str,
        subject_id: str,
        event_type: str,
        event_time: datetime,
        payload: dict,
        previous_hash: str | None,
    ) -> str:
        """Compute hash for event data using configured algorithm"""
        base = "|".join(
            [
                tenant_id,
                subject_id,
                event_type,
                event_time.isoformat(),
                self.canonical_json(payload),
                previous_hash or "GENESIS",
            ]
        )
        return self.algorithm.hash(base)
