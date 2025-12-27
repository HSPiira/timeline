"""
Workflow automation models for event-driven actions.

Workflows define triggers and actions:
- Trigger: event_type to watch for
- Actions: what to do when triggered (create event, notify, etc.)
"""
from sqlalchemy import Column, String, Text, Boolean, ForeignKey, Integer, JSON, DateTime
from sqlalchemy.sql import func
from core.database import Base
from utils.generators import generate_cuid


class Workflow(Base):
    """
    Event-driven workflow definition.

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

    id = Column(String, primary_key=True, default=generate_cuid)
    tenant_id = Column(
        String,
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Workflow metadata
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    # Trigger configuration
    trigger_event_type = Column(
        String,
        nullable=False,
        index=True,
        comment="Event type that triggers this workflow"
    )
    trigger_conditions = Column(
        JSON,
        nullable=True,
        comment="Optional JSON conditions (JSONPath expressions)"
    )

    # Actions to execute
    actions = Column(
        JSON,
        nullable=False,
        comment="Array of actions to execute [{type, params}, ...]"
    )

    # Execution settings
    max_executions_per_day = Column(
        Integer,
        nullable=True,
        comment="Rate limit: max executions per day (null = unlimited)"
    )
    execution_order = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Execution priority (lower = earlier)"
    )

    # Audit
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Workflow(id={self.id}, name={self.name}, trigger={self.trigger_event_type})>"


class WorkflowExecution(Base):
    """
    Audit trail for workflow executions.

    Tracks each time a workflow is triggered and executed.
    """
    __tablename__ = "workflow_execution"

    id = Column(String, primary_key=True, default=generate_cuid)
    tenant_id = Column(
        String,
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    workflow_id = Column(
        String,
        ForeignKey("workflow.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Trigger context
    triggered_by_event_id = Column(
        String,
        ForeignKey("event.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Event that triggered this workflow"
    )
    triggered_by_subject_id = Column(
        String,
        ForeignKey("subject.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Execution status
    status = Column(
        String,
        nullable=False,
        default="pending",
        comment="pending | running | completed | failed"
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Execution results
    actions_executed = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of actions successfully executed"
    )
    actions_failed = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of actions that failed"
    )
    execution_log = Column(
        JSON,
        nullable=True,
        comment="Detailed execution log with action results"
    )
    error_message = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    def __repr__(self):
        return f"<WorkflowExecution(id={self.id}, workflow_id={self.workflow_id}, status={self.status})>"
