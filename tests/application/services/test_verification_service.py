"""Unit tests for VerificationService"""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from src.application.services.hash_service import HashService
from src.application.services.verification_service import VerificationService
from src.infrastructure.persistence.models.event import Event


@pytest.fixture
def hash_service():
    """Hash service for testing"""
    return HashService()


@pytest.fixture
def mock_event_repo():
    """Mock event repository"""
    return AsyncMock()


@pytest.fixture
def verification_service(mock_event_repo, hash_service):
    """VerificationService instance"""
    return VerificationService(event_repo=mock_event_repo, hash_service=hash_service)


def create_test_event(
    event_id: str,
    tenant_id: str,
    subject_id: str,
    event_type: str,
    payload: dict,
    previous_hash: str | None = None,
    hash_service: HashService | None = None,
) -> Event:
    """Helper to create test event with valid hash"""
    event_time = datetime.utcnow()

    if hash_service is None:
        hash_service = HashService()

    computed_hash = hash_service.compute_hash(
        tenant_id=tenant_id,
        subject_id=subject_id,
        event_type=event_type,
        event_time=event_time,
        payload=payload,
        previous_hash=previous_hash,
    )

    event = Event(
        id=event_id,
        tenant_id=tenant_id,
        subject_id=subject_id,
        event_type=event_type,
        event_time=event_time,
        payload=payload,
        hash=computed_hash,
        previous_hash=previous_hash,
    )

    return event


class TestVerifySubjectChain:
    """Tests for verify_subject_chain method"""

    @pytest.mark.asyncio
    async def test_empty_chain_valid(self, verification_service, mock_event_repo):
        """
        GIVEN no events for subject
        WHEN verifying chain
        THEN should return valid result
        """
        # GIVEN
        mock_event_repo.get_by_subject.return_value = []

        # WHEN
        result = await verification_service.verify_subject_chain(
            subject_id="subj_123", tenant_id="tenant_123"
        )

        # THEN
        assert result.is_chain_valid is True
        assert result.total_events == 0
        assert result.valid_events == 0
        assert result.invalid_events == 0

    @pytest.mark.asyncio
    async def test_single_genesis_event_valid(
        self, verification_service, mock_event_repo, hash_service
    ):
        """
        GIVEN single genesis event
        WHEN verifying chain
        THEN should return valid
        """
        # GIVEN
        event = create_test_event(
            event_id="evt_1",
            tenant_id="tenant_123",
            subject_id="subj_123",
            event_type="created",
            payload={"test": "data"},
            previous_hash=None,
            hash_service=hash_service,
        )
        mock_event_repo.get_by_subject.return_value = [event]

        # WHEN
        result = await verification_service.verify_subject_chain(
            subject_id="subj_123", tenant_id="tenant_123"
        )

        # THEN
        assert result.is_chain_valid is True
        assert result.total_events == 1
        assert result.valid_events == 1
        assert result.invalid_events == 0

    @pytest.mark.asyncio
    async def test_multi_event_chain_valid(
        self, verification_service, mock_event_repo, hash_service
    ):
        """
        GIVEN chain of 3 valid events
        WHEN verifying chain
        THEN all should be valid
        """
        # GIVEN
        event1 = create_test_event(
            event_id="evt_1",
            tenant_id="tenant_123",
            subject_id="subj_123",
            event_type="created",
            payload={"step": 1},
            previous_hash=None,
            hash_service=hash_service,
        )

        event2 = create_test_event(
            event_id="evt_2",
            tenant_id="tenant_123",
            subject_id="subj_123",
            event_type="updated",
            payload={"step": 2},
            previous_hash=event1.hash,
            hash_service=hash_service,
        )

        event3 = create_test_event(
            event_id="evt_3",
            tenant_id="tenant_123",
            subject_id="subj_123",
            event_type="completed",
            payload={"step": 3},
            previous_hash=event2.hash,
            hash_service=hash_service,
        )

        mock_event_repo.get_by_subject.return_value = [event1, event2, event3]

        # WHEN
        result = await verification_service.verify_subject_chain(
            subject_id="subj_123", tenant_id="tenant_123"
        )

        # THEN
        assert result.is_chain_valid is True
        assert result.total_events == 3
        assert result.valid_events == 3
        assert result.invalid_events == 0

    @pytest.mark.asyncio
    async def test_tampered_event_detected(
        self, verification_service, mock_event_repo, hash_service
    ):
        """
        GIVEN event with modified payload (hash mismatch)
        WHEN verifying chain
        THEN tampering should be detected
        """
        # GIVEN
        event = create_test_event(
            event_id="evt_1",
            tenant_id="tenant_123",
            subject_id="subj_123",
            event_type="created",
            payload={"amount": 100},
            previous_hash=None,
            hash_service=hash_service,
        )

        # Tamper with payload (simulating malicious modification)
        event.payload = {"amount": 999}  # Changed from 100!
        # Hash remains the same (computed from original payload)

        mock_event_repo.get_by_subject.return_value = [event]

        # WHEN
        result = await verification_service.verify_subject_chain(
            subject_id="subj_123", tenant_id="tenant_123"
        )

        # THEN
        assert result.is_chain_valid is False
        assert result.total_events == 1
        assert result.valid_events == 0
        assert result.invalid_events == 1
        assert result.event_results[0].error_type == "HASH_MISMATCH"

    @pytest.mark.asyncio
    async def test_broken_chain_detected(self, verification_service, mock_event_repo, hash_service):
        """
        GIVEN events with broken previous_hash link
        WHEN verifying chain
        THEN chain break should be detected
        """
        # GIVEN
        event1 = create_test_event(
            event_id="evt_1",
            tenant_id="tenant_123",
            subject_id="subj_123",
            event_type="created",
            payload={"step": 1},
            previous_hash=None,
            hash_service=hash_service,
        )

        event2 = create_test_event(
            event_id="evt_2",
            tenant_id="tenant_123",
            subject_id="subj_123",
            event_type="updated",
            payload={"step": 2},
            previous_hash="wrong_hash",  # Should be event1.hash!
            hash_service=hash_service,
        )

        mock_event_repo.get_by_subject.return_value = [event1, event2]

        # WHEN
        result = await verification_service.verify_subject_chain(
            subject_id="subj_123", tenant_id="tenant_123"
        )

        # THEN
        assert result.is_chain_valid is False
        assert result.invalid_events == 1
        assert result.event_results[1].error_type == "CHAIN_BREAK"
        assert result.event_results[1].expected_hash == event1.hash
        assert result.event_results[1].actual_hash == "wrong_hash"


class TestVerifyTenantChains:
    """Tests for verify_tenant_chains method"""

    @pytest.mark.asyncio
    async def test_multiple_subjects_all_valid(
        self, verification_service, mock_event_repo, hash_service
    ):
        """
        GIVEN multiple subjects with valid chains
        WHEN verifying tenant chains
        THEN all should be valid
        """
        # GIVEN - Subject A events
        event_a1 = create_test_event(
            event_id="evt_a1",
            tenant_id="tenant_123",
            subject_id="subj_a",
            event_type="created",
            payload={"data": "a1"},
            previous_hash=None,
            hash_service=hash_service,
        )

        event_a2 = create_test_event(
            event_id="evt_a2",
            tenant_id="tenant_123",
            subject_id="subj_a",
            event_type="updated",
            payload={"data": "a2"},
            previous_hash=event_a1.hash,
            hash_service=hash_service,
        )

        # Subject B events
        event_b1 = create_test_event(
            event_id="evt_b1",
            tenant_id="tenant_123",
            subject_id="subj_b",
            event_type="created",
            payload={"data": "b1"},
            previous_hash=None,
            hash_service=hash_service,
        )

        mock_event_repo.get_by_tenant.return_value = [event_a1, event_a2, event_b1]

        # WHEN
        result = await verification_service.verify_tenant_chains(tenant_id="tenant_123", limit=100)

        # THEN
        assert result.is_chain_valid is True
        assert result.total_events == 3
        assert result.valid_events == 3
        assert result.invalid_events == 0

    @pytest.mark.asyncio
    async def test_one_subject_invalid_detected(
        self, verification_service, mock_event_repo, hash_service
    ):
        """
        GIVEN multiple subjects, one with tampered event
        WHEN verifying tenant chains
        THEN tampering should be detected
        """
        # GIVEN - Valid subject
        event_a1 = create_test_event(
            event_id="evt_a1",
            tenant_id="tenant_123",
            subject_id="subj_a",
            event_type="created",
            payload={"data": "a1"},
            previous_hash=None,
            hash_service=hash_service,
        )

        # Tampered subject
        event_b1 = create_test_event(
            event_id="evt_b1",
            tenant_id="tenant_123",
            subject_id="subj_b",
            event_type="created",
            payload={"amount": 100},
            previous_hash=None,
            hash_service=hash_service,
        )
        event_b1.payload = {"amount": 999}  # Tampered!

        mock_event_repo.get_by_tenant.return_value = [event_a1, event_b1]

        # WHEN
        result = await verification_service.verify_tenant_chains(tenant_id="tenant_123", limit=100)

        # THEN
        assert result.is_chain_valid is False
        assert result.total_events == 2
        assert result.valid_events == 1
        assert result.invalid_events == 1
