from datetime import datetime
import pytest
from src.application.services.hash_service import HashService, SHA256Algorithm
from freezegun import freeze_time

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
        THEN the 'previous_hash' part of the hash input should be 'GENESIS'.
        """
        # GIVEN
        tenant_id = "tenant-123"
        subject_id = "subject-456"
        event_type = "TEST_EVENT"
        payload = {"data": "value"}
        previous_hash = None

        # WHEN
        event_hash = hash_service.compute_hash(
            tenant_id=tenant_id,
            subject_id=subject_id,
            event_type=event_type,
            event_time=FROZEN_DATETIME,
            payload=payload,
            previous_hash=previous_hash,
        )

        # THEN
        # The expected hash is a SHA256 of the canonical parts joined by '|'
        # tenant|subject|type|timestamp|payload|GENESIS
        expected_base = (
            "tenant-123|subject-456|TEST_EVENT|2023-01-01T12:00:00+00:00|"
            '{"data":"value"}|GENESIS'
        )
        expected_hash = "c187653198a0d273767f73956f43734e02b6659a4336d3a146a815777a4521f5"
        assert event_hash == expected_hash

    @freeze_time(FROZEN_TIME)
    def test_compute_hash_subsequent_event(self, hash_service: HashService):
        """
        GIVEN a subject with a previous event
        WHEN the hash for a new event is computed
        THEN the hash must include the previous event's hash, creating a chain.
        """
        # GIVEN
        tenant_id = "tenant-123"
        subject_id = "subject-456"
        event_type = "TEST_EVENT"
        payload = {"data": "new_value"}
        previous_hash = "c187653198a0d273767f73956f43734e02b6659a4336d3a146a815777a4521f5"

        # WHEN
        event_hash = hash_service.compute_hash(
            tenant_id=tenant_id,
            subject_id=subject_id,
            event_type=event_type,
            event_time=FROZEN_DATETIME,
            payload=payload,
            previous_hash=previous_hash,
        )

        # THEN
        # The base string now includes the actual previous hash
        expected_base = (
            "tenant-123|subject-456|TEST_EVENT|2023-01-01T12:00:00+00:00|"
            '{"data":"new_value"}|'
            "c187653198a0d273767f73956f43734e02b6659a4336d3a146a815777a4521f5"
        )
        expected_hash = "b5a9b83a73c1505315206380619e06180637048731d102061f1c7d81223e7512"
        assert event_hash == expected_hash
