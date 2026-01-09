"""Test event repository"""

from datetime import datetime, timedelta, timezone

import pytest

from src.infrastructure.persistence.models.event import Event
from src.infrastructure.persistence.models.subject import Subject
from src.infrastructure.persistence.models.tenant import Tenant
from src.infrastructure.persistence.repositories.event_repo import \
    EventRepository


@pytest.fixture
async def event_repo(test_db):
    """Event repository fixture"""
    return EventRepository(test_db)


@pytest.fixture
async def second_tenant(test_db):
    """Create second tenant for isolation tests"""
    tenant = Tenant(
        id="tenant-2", code="TENANT2", name="Second Tenant", status="active", is_active=True
    )
    test_db.add(tenant)
    await test_db.commit()
    await test_db.refresh(tenant)
    return tenant


@pytest.fixture
async def second_subject(test_db, second_tenant):
    """Create subject for second tenant"""
    subject = Subject(
        id="subject-2", tenant_id=second_tenant.id, subject_type="user", external_ref="user-456"
    )
    test_db.add(subject)
    await test_db.commit()
    await test_db.refresh(subject)
    return subject


@pytest.mark.asyncio
async def test_get_last_event_returns_most_recent(event_repo, test_db, test_subject, test_tenant):
    """Test that get_last_event returns the most recent event"""
    # Create events with different timestamps
    event1 = Event(
        tenant_id=test_tenant.id,
        subject_id=test_subject.id,
        event_type="test",
        schema_version=1,
        event_time=datetime.now(timezone.utc) - timedelta(hours=2),
        payload={"step": 1},
        hash="hash1",
    )
    event2 = Event(
        tenant_id=test_tenant.id,
        subject_id=test_subject.id,
        event_type="test",
        schema_version=1,
        event_time=datetime.now(timezone.utc) - timedelta(hours=1),
        payload={"step": 2},
        hash="hash2",
        previous_hash="hash1",
    )
    event3 = Event(
        tenant_id=test_tenant.id,
        subject_id=test_subject.id,
        event_type="test",
        schema_version=1,
        event_time=datetime.now(timezone.utc),
        payload={"step": 3},
        hash="hash3",
        previous_hash="hash2",
    )

    test_db.add_all([event1, event2, event3])
    await test_db.commit()

    # Get last event
    last_event = await event_repo.get_last_event(test_subject.id, test_tenant.id)

    assert last_event is not None
    assert last_event.hash == "hash3"
    assert last_event.previous_hash == "hash2"
    assert last_event.payload["step"] == 3


@pytest.mark.asyncio
async def test_get_last_event_empty_subject(event_repo, test_subject, test_tenant):
    """Test get_last_event with no events"""
    last_event = await event_repo.get_last_event(test_subject.id, test_tenant.id)
    assert last_event is None


@pytest.mark.asyncio
async def test_tenant_isolation_in_get_last_event(
    event_repo, test_db, test_subject, test_tenant, second_subject, second_tenant
):
    """Test that get_last_event enforces tenant isolation"""
    # Create event for tenant 1
    event1 = Event(
        tenant_id=test_tenant.id,
        subject_id=test_subject.id,
        event_type="test",
        schema_version=1,
        event_time=datetime.now(timezone.utc),
        payload={"tenant": 1},
        hash="hash1",
    )

    # Create event for tenant 2
    event2 = Event(
        tenant_id=second_tenant.id,
        subject_id=second_subject.id,
        event_type="test",
        schema_version=1,
        event_time=datetime.now(timezone.utc),
        payload={"tenant": 2},
        hash="hash2",
    )

    test_db.add_all([event1, event2])
    await test_db.commit()

    # Try to fetch tenant 1's event with wrong tenant
    result = await event_repo.get_last_event(test_subject.id, second_tenant.id)
    assert result is None  # Should not find event from different tenant


@pytest.mark.asyncio
async def test_get_by_subject_returns_ordered_events(
    event_repo, test_db, test_subject, test_tenant
):
    """Test that get_by_subject returns events ordered by time descending"""
    # Create events
    times = [
        datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
        datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    ]

    for i, event_time in enumerate(times):
        event = Event(
            tenant_id=test_tenant.id,
            subject_id=test_subject.id,
            event_type="test",
            schema_version=1,
            event_time=event_time,
            payload={"order": i},
            hash=f"hash{i}",
        )
        test_db.add(event)

    await test_db.commit()

    # Get events
    events = await event_repo.get_by_subject(test_subject.id, test_tenant.id)

    # Should be ordered by time descending (most recent first)
    assert len(events) == 3
    assert events[0].payload["order"] == 2  # Latest
    assert events[1].payload["order"] == 1
    assert events[2].payload["order"] == 0  # Oldest


@pytest.mark.asyncio
async def test_get_by_subject_pagination(event_repo, test_db, test_subject, test_tenant):
    """Test pagination in get_by_subject"""
    # Create 10 events
    for i in range(10):
        event = Event(
            tenant_id=test_tenant.id,
            subject_id=test_subject.id,
            event_type="test",
            schema_version=1,
            event_time=datetime.now(timezone.utc) + timedelta(seconds=i),
            payload={"index": i},
            hash=f"hash{i}",
        )
        test_db.add(event)

    await test_db.commit()

    # Get first page (5 items)
    page1 = await event_repo.get_by_subject(test_subject.id, test_tenant.id, skip=0, limit=5)
    assert len(page1) == 5

    # Get second page (5 items)
    page2 = await event_repo.get_by_subject(test_subject.id, test_tenant.id, skip=5, limit=5)
    assert len(page2) == 5

    # Verify no overlap
    page1_hashes = {e.hash for e in page1}
    page2_hashes = {e.hash for e in page2}
    assert page1_hashes.isdisjoint(page2_hashes)


@pytest.mark.asyncio
async def test_get_last_hash_returns_previous_hash(event_repo, test_db, test_subject, test_tenant):
    """Test get_last_hash returns the hash of the most recent event"""
    # Create chained events
    event1 = Event(
        tenant_id=test_tenant.id,
        subject_id=test_subject.id,
        event_type="test",
        schema_version=1,
        event_time=datetime.now(timezone.utc) - timedelta(hours=1),
        payload={},
        hash="hash1",
    )
    event2 = Event(
        tenant_id=test_tenant.id,
        subject_id=test_subject.id,
        event_type="test",
        schema_version=1,
        event_time=datetime.now(timezone.utc),
        payload={},
        hash="hash2",
        previous_hash="hash1",
    )

    test_db.add_all([event1, event2])
    await test_db.commit()

    # Get last hash
    last_hash = await event_repo.get_last_hash(test_subject.id, test_tenant.id)
    assert last_hash == "hash2"


@pytest.mark.asyncio
async def test_get_last_hash_none_for_empty_subject(event_repo, test_subject, test_tenant):
    """Test get_last_hash returns None for subject with no events"""
    last_hash = await event_repo.get_last_hash(test_subject.id, test_tenant.id)
    assert last_hash is None


@pytest.mark.asyncio
async def test_get_by_id_and_tenant(event_repo, test_db, test_subject, test_tenant, second_tenant):
    """Test get_by_id_and_tenant enforces tenant isolation"""
    # Create event for tenant 1
    event = Event(
        id="event-123",
        tenant_id=test_tenant.id,
        subject_id=test_subject.id,
        event_type="test",
        schema_version=1,
        event_time=datetime.now(timezone.utc),
        payload={},
        hash="hash1",
    )
    test_db.add(event)
    await test_db.commit()

    # Should find with correct tenant
    found = await event_repo.get_by_id_and_tenant("event-123", test_tenant.id)
    assert found is not None
    assert found.id == "event-123"

    # Should NOT find with wrong tenant
    not_found = await event_repo.get_by_id_and_tenant("event-123", second_tenant.id)
    assert not_found is None


@pytest.mark.asyncio
async def test_event_immutability_enforcement(test_db, test_subject, test_tenant):
    """Test that events cannot be updated after creation"""
    # Create event
    event = Event(
        tenant_id=test_tenant.id,
        subject_id=test_subject.id,
        event_type="test",
        schema_version=1,
        event_time=datetime.now(timezone.utc),
        payload={"original": "value"},
        hash="hash1",
    )
    test_db.add(event)
    await test_db.commit()

    # Try to update event (should raise ValueError from ORM listener)
    event.payload = {"modified": "value"}

    with pytest.raises(ValueError, match="Events are immutable"):
        await test_db.flush()
