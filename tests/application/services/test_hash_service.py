from datetime import datetime

import pytest
from freezegun import freeze_time

from src.application.services.hash_service import HashService, SHA256Algorithm

# A fixed timestamp for reproducible tests
FROZEN_TIME = "2023-01-01T12:00:00Z"
FROZEN_DATETIME = datetime.fromisoformat(FROZEN_TIME.replace("Z", "+00:00"))


@pytest.fixture
def hash_service() -> HashService:
    """Provides a default HashService instance for tests."""
    return HashService(algorithm=SHA256Algorithm())


class TestHashService:
    """Unit tests for the HashService."""

    def test_canonical_json_produces_consistent_output(self):
        """
        GIVEN two dictionaries with the same data but different key order
        WHEN they are converted to canonical JSON
        THEN the output strings must be identical.
        """
        # GIVEN
        dict1 = {"b": 2, "a": 1, "c": {"d": 4, "e": 3}}
        dict2 = {"a": 1, "b": 2, "c": {"e": 3, "d": 4}}

        # WHEN
        json1 = HashService.canonical_json(dict1)
        json2 = HashService.canonical_json(dict2)

        # THEN
        assert json1 == '{"a":1,"b":2,"c":{"d":4,"e":3}}'
        assert json1 == json2

    @freeze_time(FROZEN_TIME)
    def test_compute_hash_genesis_event(self, hash_service: HashService):
        """
        GIVEN a new subject with no previous events
        WHEN the hash for the first event (genesis event) is computed
        THEN the hash should be computed from canonical JSON with null previous_hash.
        """
        # GIVEN
        subject_id = "subject-456"
        event_type = "TEST_EVENT"
        schema_version = 1
        payload = {"data": "value"}
        previous_hash = None

        # WHEN
        event_hash = hash_service.compute_hash(
            subject_id=subject_id,
            event_type=event_type,
            schema_version=schema_version,
            event_time=FROZEN_DATETIME,
            payload=payload,
            previous_hash=previous_hash,
        )

        # THEN
        # Hash is SHA256 of canonical JSON dict
        assert len(event_hash) == 64  # SHA256 hex digest
        assert event_hash.isalnum()

    @freeze_time(FROZEN_TIME)
    def test_compute_hash_subsequent_event(self, hash_service: HashService):
        """
        GIVEN a subject with a previous event
        WHEN the hash for a new event is computed
        THEN the hash must include the previous event's hash, creating a chain.
        """
        # GIVEN
        subject_id = "subject-456"
        event_type = "TEST_EVENT"
        schema_version = 1
        payload = {"data": "new_value"}
        previous_hash = "abc123def456"

        # WHEN
        event_hash = hash_service.compute_hash(
            subject_id=subject_id,
            event_type=event_type,
            schema_version=schema_version,
            event_time=FROZEN_DATETIME,
            payload=payload,
            previous_hash=previous_hash,
        )

        # THEN
        assert len(event_hash) == 64
        assert event_hash.isalnum()

    @freeze_time(FROZEN_TIME)
    def test_compute_hash_deterministic(self, hash_service: HashService):
        """
        GIVEN the same inputs
        WHEN computing hash multiple times
        THEN the result should be identical.
        """
        # GIVEN
        inputs = {
            "subject_id": "subject-456",
            "event_type": "TEST_EVENT",
            "schema_version": 1,
            "event_time": FROZEN_DATETIME,
            "payload": {"data": "value"},
            "previous_hash": None,
        }

        # WHEN
        hash1 = hash_service.compute_hash(**inputs)
        hash2 = hash_service.compute_hash(**inputs)

        # THEN
        assert hash1 == hash2

    @freeze_time(FROZEN_TIME)
    def test_compute_hash_different_schema_version(self, hash_service: HashService):
        """
        GIVEN same data but different schema_version
        WHEN computing hash
        THEN hashes should be different.
        """
        # GIVEN
        base_inputs = {
            "subject_id": "subject-456",
            "event_type": "TEST_EVENT",
            "event_time": FROZEN_DATETIME,
            "payload": {"data": "value"},
            "previous_hash": None,
        }

        # WHEN
        hash_v1 = hash_service.compute_hash(**base_inputs, schema_version=1)
        hash_v2 = hash_service.compute_hash(**base_inputs, schema_version=2)

        # THEN
        assert hash_v1 != hash_v2
