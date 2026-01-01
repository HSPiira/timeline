"""Test event API endpoints"""

from datetime import datetime, timezone

import pytest
from fastapi import status


@pytest.mark.asyncio
async def test_create_event_success(client, auth_headers, test_subject):
    """Test successful event creation"""
    response = await client.post(
        "/events/",
        json={
            "subject_id": test_subject.id,
            "event_type": "test_event",
            "schema_version": 1,
            "event_time": datetime.now(timezone.utc).isoformat(),
            "payload": {"key": "value", "test": True},
        },
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["subject_id"] == test_subject.id
    assert data["event_type"] == "test_event"
    assert "hash" in data
    assert "id" in data
    assert data["previous_hash"] is None  # First event


@pytest.mark.asyncio
async def test_create_event_unauthorized(client, test_subject):
    """Test event creation without authentication"""
    response = await client.post(
        "/events/",
        json={
            "subject_id": test_subject.id,
            "event_type": "test_event",
            "schema_version": 1,
            "event_time": datetime.now(timezone.utc).isoformat(),
            "payload": {},
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_create_event_invalid_subject(client, auth_headers):
    """Test event creation with non-existent subject"""
    response = await client.post(
        "/events/",
        json={
            "subject_id": "non-existent-subject",
            "event_type": "test_event",
            "schema_version": 1,
            "event_time": datetime.now(timezone.utc).isoformat(),
            "payload": {},
        },
        headers=auth_headers,
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_event_chain_integrity(client, auth_headers, test_subject):
    """Test cryptographic event chaining"""
    # Create first event
    response1 = await client.post(
        "/events/",
        json={
            "subject_id": test_subject.id,
            "event_type": "event1",
            "schema_version": 1,
            "event_time": "2025-01-01T10:00:00Z",
            "payload": {"step": 1},
        },
        headers=auth_headers,
    )
    assert response1.status_code == status.HTTP_201_CREATED
    event1 = response1.json()

    # Create second event
    response2 = await client.post(
        "/events/",
        json={
            "subject_id": test_subject.id,
            "event_type": "event2",
            "schema_version": 1,
            "event_time": "2025-01-01T11:00:00Z",
            "payload": {"step": 2},
        },
        headers=auth_headers,
    )
    assert response2.status_code == status.HTTP_201_CREATED
    event2 = response2.json()

    # Verify chain
    assert event2["previous_hash"] == event1["hash"]
    assert event1["previous_hash"] is None


@pytest.mark.asyncio
async def test_get_events_by_subject(client, auth_headers, test_subject):
    """Test retrieving events for a subject"""
    # Create two events
    for i in range(2):
        await client.post(
            "/events/",
            json={
                "subject_id": test_subject.id,
                "event_type": f"event{i}",
                "schema_version": 1,
                "event_time": f"2025-01-01T{10+i}:00:00Z",
                "payload": {"step": i},
            },
            headers=auth_headers,
        )

    # Get events
    response = await client.get(f"/events/?subject_id={test_subject.id}", headers=auth_headers)

    assert response.status_code == 200
    events = response.json()
    assert len(events) == 2
