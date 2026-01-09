"""
System Audit Schema Definition.

Defines the JSON Schema for system audit events with strict validation.
This schema is created during tenant initialization and used for all
internal CRUD audit tracking.
"""

from typing import Any

# Reserved event type for system audit events
SYSTEM_AUDIT_EVENT_TYPE = "system.audit"

# Reserved subject type for system audit trail
SYSTEM_AUDIT_SUBJECT_TYPE = "system_audit"
SYSTEM_AUDIT_SUBJECT_REF = "_system_audit_trail"

# Current schema version - increment when making breaking changes
SYSTEM_AUDIT_SCHEMA_VERSION = 1

# Supported entity types that can be audited
AUDITABLE_ENTITIES = frozenset({
    "subject",
    "event_schema",
    "workflow",
    "user",
    "role",
    "permission",
    "document",
    "tenant",
    "email_account",
    "oauth_provider",
})

# Supported audit actions
AUDIT_ACTIONS = frozenset({
    "created",
    "updated",
    "deleted",
    "activated",
    "deactivated",
    "assigned",
    "unassigned",
    "status_changed",
})

# Actor types that can perform auditable actions
ACTOR_TYPES = frozenset({
    "user",
    "system",
    "external",
    "api_key",
    "webhook",
})


def get_system_audit_schema_definition() -> dict[str, Any]:
    """
    Returns the JSON Schema definition for system audit events.

    This schema enforces:
    - Required fields for all audit events
    - Enumerated values for entity_type, action, and actor_type
    - Structured entity_data and metadata objects
    - No additional properties (strict validation)

    The schema is designed to be:
    - Immutable: Once created, audit events cannot be modified
    - Complete: All necessary context is captured
    - Queryable: Structured for efficient filtering and searching
    - Secure: Sensitive data is expected to be sanitized before storage
    """
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "System Audit Event",
        "description": "Schema for tracking all system CRUD operations",
        "type": "object",
        "required": ["entity_type", "entity_id", "action", "actor", "timestamp"],
        "additionalProperties": False,
        "properties": {
            "entity_type": {
                "type": "string",
                "description": "Type of entity being audited",
                "enum": list(AUDITABLE_ENTITIES),
            },
            "entity_id": {
                "type": "string",
                "description": "CUID of the affected entity",
                "minLength": 1,
                "maxLength": 128,
            },
            "action": {
                "type": "string",
                "description": "The action performed on the entity",
                "enum": list(AUDIT_ACTIONS),
            },
            "actor": {
                "type": "object",
                "description": "Who or what performed the action",
                "required": ["type"],
                "additionalProperties": False,
                "properties": {
                    "type": {
                        "type": "string",
                        "description": "Type of actor",
                        "enum": list(ACTOR_TYPES),
                    },
                    "id": {
                        "type": ["string", "null"],
                        "description": "ID of the actor (user ID, API key ID, etc.)",
                        "maxLength": 128,
                    },
                    "ip_address": {
                        "type": ["string", "null"],
                        "description": "IP address of the request origin",
                        "maxLength": 45,  # IPv6 max length
                    },
                    "user_agent": {
                        "type": ["string", "null"],
                        "description": "User agent string",
                        "maxLength": 512,
                    },
                },
            },
            "timestamp": {
                "type": "string",
                "description": "ISO 8601 timestamp of when the action occurred",
                "format": "date-time",
            },
            "entity_data": {
                "type": "object",
                "description": "Snapshot of the entity at the time of the action",
                "additionalProperties": True,  # Allow any entity structure
            },
            "changes": {
                "type": ["object", "null"],
                "description": "For updates: the fields that changed with before/after values",
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "before": {},
                        "after": {},
                    },
                },
            },
            "metadata": {
                "type": "object",
                "description": "Additional context about the operation",
                "additionalProperties": True,
                "properties": {
                    "request_id": {
                        "type": ["string", "null"],
                        "description": "Correlation ID for request tracing",
                    },
                    "reason": {
                        "type": ["string", "null"],
                        "description": "Human-readable reason for the action",
                    },
                    "source": {
                        "type": ["string", "null"],
                        "description": "Source of the action (api, webhook, scheduler, etc.)",
                    },
                },
            },
        },
    }


def validate_audit_payload(payload: dict[str, Any]) -> list[str]:
    """
    Validate an audit payload against the schema without raising exceptions.

    Returns a list of validation errors (empty list if valid).
    This is useful for pre-validation before event creation.
    """
    import jsonschema

    schema = get_system_audit_schema_definition()
    validator = jsonschema.Draft7Validator(schema)
    return [error.message for error in validator.iter_errors(payload)]
