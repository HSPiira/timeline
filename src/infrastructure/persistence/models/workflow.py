"""
Workflow automation models for event-driven actions.

Workflows define triggers and actions:
- Trigger: event_type to watch for
- Actions: what to do when triggered (create event, notify, etc.)
"""
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models.mixins import (
    AuditedMultiTenantModel,
    MultiTenantModel,
)


class Workflow(AuditedMultiTenantModel, Base):
    """
    Event-driven workflow definition.

    Inherits from AuditedMultiTenantModel:
        - id: CUID primary key
        - tenant_id: Foreign key to tenant
        - created_at, updated_at: Timestamps
        - created_by, updated_by, deleted_by: User tracking
        - deleted_at: Soft delete support

    Example workflow:
    {
        "name": "Auto-escalate urgent issues",
        "trigger": {
            "event_type": "issue_created",
            "conditions": {
                "payload.priority": "urgent"
            }
        },
        "actions": [
            {
                "type": "create_event",
                "params": {
                    "event_type": "issue_escalated",
                    "payload": {
                        "escalated_by": "workflow",
                        "reason": "auto_urgent"
                    }
                }
            }
        ]
    }
    """

    __tablename__ = "workflow"

    # Workflow metadata
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Trigger configuration
    trigger_event_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
        comment="Event type that triggers this workflow",
    )
    trigger_conditions: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Optional JSON conditions (JSONPath expressions)"
    )

    # Actions to execute
    actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        comment="Array of actions to execute [{type, params}, ...]",
    )

    # Execution settings
    max_executions_per_day: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Rate limit: max executions per day (null = unlimited)",
    )
    execution_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Execution priority (lower = earlier)",
    )

    def __repr__(self):
        return f"<Workflow(id={self.id}, name={self.name}, trigger={self.trigger_event_type})>"


class WorkflowExecution(MultiTenantModel, Base):
    """
    Audit trail for workflow executions.

    Inherits from MultiTenantModel:
        - id: CUID primary key
        - tenant_id: Foreign key to tenant
        - created_at: Creation timestamp
        - updated_at: Last update timestamp

    Tracks each time a workflow is triggered and executed.
    """

    __tablename__ = "workflow_execution"

    workflow_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("workflow.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Trigger context
    triggered_by_event_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("event.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Event that triggered this workflow",
    )
    triggered_by_subject_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("subject.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Execution status
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="pending",
        comment="pending | running | completed | failed",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Execution results
    actions_executed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of actions successfully executed",
    )
    actions_failed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Number of actions that failed"
    )
    execution_log: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True, comment="Detailed execution log with action results"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self):
        return f"<WorkflowExecution(id={self.id}, workflow_id={self.workflow_id}, status={self.status})>"
