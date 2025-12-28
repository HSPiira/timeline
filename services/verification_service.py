"""
Chain verification service for cryptographic integrity validation.

Verifies that event chains are intact and untampered by:
1. Recomputing each event's hash
2. Validating hash matches stored value
3. Verifying previous_hash links form unbroken chain
"""
from datetime import datetime

from models.event import Event
from repositories.event_repo import EventRepository
from services.hash_service import HashService


class VerificationResult:
    """Result of chain verification for a single event."""

    def __init__(
        self,
        event_id: str,
        event_type: str,
        event_time: datetime,
        sequence: int,
        is_valid: bool,
        error_type: str | None = None,
        error_message: str | None = None,
        expected_hash: str | None = None,
        actual_hash: str | None = None,
    ):
        self.event_id = event_id
        self.event_type = event_type
        self.event_time = event_time
        self.sequence = sequence
        self.is_valid = is_valid
        self.error_type = error_type
        self.error_message = error_message
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash


class ChainVerificationResult:
    """Result of chain verification for a subject or tenant."""

    def __init__(
        self,
        subject_id: str | None,
        tenant_id: str,
        total_events: int,
        valid_events: int,
        invalid_events: int,
        is_chain_valid: bool,
        verified_at: datetime,
        event_results: list[VerificationResult],
    ):
        self.subject_id = subject_id
        self.tenant_id = tenant_id
        self.total_events = total_events
        self.valid_events = valid_events
        self.invalid_events = invalid_events
        self.is_chain_valid = is_chain_valid
        self.verified_at = verified_at
        self.event_results = event_results


class VerificationService:
    """
    Service for verifying cryptographic integrity of event chains.

    Validation checks:
    1. Hash integrity - recomputed hash matches stored hash
    2. Chain continuity - previous_hash links are correct
    3. Sequence order - events are in correct chronological order
    """

    def __init__(self, event_repo: EventRepository, hash_service: HashService):
        self.event_repo = event_repo
        self.hash_service = hash_service

    async def verify_subject_chain(
        self, subject_id: str, tenant_id: str
    ) -> ChainVerificationResult:
        """
        Verify event chain for a single subject.

        Args:
            subject_id: Subject to verify
            tenant_id: Tenant ID for access control

        Returns:
            ChainVerificationResult with detailed verification status
        """
        # Get all events for subject and sort in chronological order (oldest first)
        events = await self.event_repo.get_by_subject(subject_id, tenant_id)
        # Repository returns DESC order, but verification needs ASC (oldest first)
        events = sorted(events, key=lambda e: e.event_time)

        if not events:
            return ChainVerificationResult(
                subject_id=subject_id,
                tenant_id=tenant_id,
                total_events=0,
                valid_events=0,
                invalid_events=0,
                is_chain_valid=True,  # Empty chain is valid
                verified_at=datetime.utcnow(),
                event_results=[],
            )

        event_results = []
        valid_count = 0
        invalid_count = 0

        for i, event in enumerate(events):
            result = self._verify_event(event, events[i - 1] if i > 0 else None, i)
            event_results.append(result)

            if result.is_valid:
                valid_count += 1
            else:
                invalid_count += 1

        return ChainVerificationResult(
            subject_id=subject_id,
            tenant_id=tenant_id,
            total_events=len(events),
            valid_events=valid_count,
            invalid_events=invalid_count,
            is_chain_valid=(invalid_count == 0),
            verified_at=datetime.utcnow(),
            event_results=event_results,
        )

    async def verify_tenant_chains(
        self, tenant_id: str, limit: int | None = None
    ) -> ChainVerificationResult:
        """
        Verify all event chains for a tenant.

        Args:
            tenant_id: Tenant ID
            limit: Optional limit on number of events to verify

        Returns:
            ChainVerificationResult aggregated across all subjects
        """
        # Get all events for tenant in chronological order
        events = await self.event_repo.get_by_tenant(tenant_id, limit=limit or 100)

        if not events:
            return ChainVerificationResult(
                subject_id=None,
                tenant_id=tenant_id,
                total_events=0,
                valid_events=0,
                invalid_events=0,
                is_chain_valid=True,
                verified_at=datetime.utcnow(),
                event_results=[],
            )

        # Group events by subject for proper chain verification
        events_by_subject: dict[str, list[Event]] = {}
        for event in events:
            if event.subject_id not in events_by_subject:
                events_by_subject[event.subject_id] = []
            events_by_subject[event.subject_id].append(event)

        # Sort each subject's events chronologically (oldest first) for verification
        for subject_id in events_by_subject:
            events_by_subject[subject_id] = sorted(
                events_by_subject[subject_id], key=lambda e: e.event_time
            )

        all_results = []
        valid_count = 0
        invalid_count = 0

        # Verify each subject's chain
        for _, subject_events in events_by_subject.items():
            for i, event in enumerate(subject_events):
                result = self._verify_event(
                    event, subject_events[i - 1] if i > 0 else None, i
                )
                all_results.append(result)

                if result.is_valid:
                    valid_count += 1
                else:
                    invalid_count += 1

        return ChainVerificationResult(
            subject_id=None,  # Multiple subjects
            tenant_id=tenant_id,
            total_events=len(events),
            valid_events=valid_count,
            invalid_events=invalid_count,
            is_chain_valid=(invalid_count == 0),
            verified_at=datetime.utcnow(),
            event_results=all_results,
        )

    def _verify_event(
        self, event: Event, previous_event: Event | None, sequence: int
    ) -> VerificationResult:
        """
        Verify a single event's integrity.

        Checks:
        1. Hash integrity - recomputed hash matches stored hash
        2. Chain link - previous_hash matches previous event's hash
        3. Genesis event - first event has no previous_hash or GENESIS

        Args:
            event: Event to verify
            previous_event: Previous event in chain (None for genesis)
            sequence: Position in chain (0-indexed)

        Returns:
            VerificationResult with validation details
        """
        # Recompute hash
        computed_hash = self.hash_service.compute_hash(
            tenant_id=event.tenant_id,
            subject_id=event.subject_id,
            event_type=event.event_type,
            event_time=event.event_time,
            payload=event.payload,
            previous_hash=event.previous_hash,
        )

        # Check 1: Hash integrity
        if computed_hash != event.hash:
            return VerificationResult(
                event_id=event.id,
                event_type=event.event_type,
                event_time=event.event_time,
                sequence=sequence,
                is_valid=False,
                error_type="HASH_MISMATCH",
                error_message="Event hash does not match recomputed hash",
                expected_hash=computed_hash,
                actual_hash=event.hash,
            )

        # Check 2: Chain linkage
        if sequence == 0:
            # Genesis event - should have no previous_hash or None
            if event.previous_hash is not None:
                return VerificationResult(
                    event_id=event.id,
                    event_type=event.event_type,
                    event_time=event.event_time,
                    sequence=sequence,
                    is_valid=False,
                    error_type="GENESIS_ERROR",
                    error_message=f"Genesis event should have null previous_hash, got: {event.previous_hash}",
                    expected_hash=None,
                    actual_hash=event.previous_hash,
                )
        else:
            # Non-genesis event - previous_hash must match previous event's hash
            if previous_event is None:
                return VerificationResult(
                    event_id=event.id,
                    event_type=event.event_type,
                    event_time=event.event_time,
                    sequence=sequence,
                    is_valid=False,
                    error_type="MISSING_PREVIOUS",
                    error_message=f"Previous event not found for sequence {sequence}",
                    expected_hash="<previous_event>",
                    actual_hash=None,
                )

            if event.previous_hash != previous_event.hash:
                return VerificationResult(
                    event_id=event.id,
                    event_type=event.event_type,
                    event_time=event.event_time,
                    sequence=sequence,
                    is_valid=False,
                    error_type="CHAIN_BREAK",
                    error_message="Chain broken: previous_hash does not match previous event's hash",
                    expected_hash=previous_event.hash,
                    actual_hash=event.previous_hash,
                )

        # All checks passed
        return VerificationResult(
            event_id=event.id,
            event_type=event.event_type,
            event_time=event.event_time,
            sequence=sequence,
            is_valid=True,
            error_type=None,
            error_message=None,
            expected_hash=event.hash,
            actual_hash=event.hash,
        )
