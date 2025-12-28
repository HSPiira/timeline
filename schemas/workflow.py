"""Pydantic schemas for workflows"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkflowCreate(BaseModel):
    """Create workflow request"""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    trigger_event_type: str = Field(..., pattern=r"^[a-z0-9_]+$")
    trigger_conditions: dict[str, Any] | None = None
    actions: list[dict[str, Any]] = Field(..., min_items=1)
    execution_order: int = Field(default=0, ge=0)
    max_executions_per_day: int | None = Field(None, gt=0)
    is_active: bool = True


class WorkflowUpdate(BaseModel):
    """Update workflow request"""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    trigger_conditions: dict[str, Any] | None = None
    actions: list[dict[str, Any]] | None = Field(None, min_items=1)
    execution_order: int | None = Field(None, ge=0)
    max_executions_per_day: int | None = Field(None, gt=0)
    is_active: bool | None = None


class WorkflowResponse(BaseModel):
    """Workflow response"""

    id: str
    tenant_id: str
    name: str
    description: str | None
    is_active: bool
    trigger_event_type: str
    trigger_conditions: dict[str, Any] | None
    actions: list[dict[str, Any]]
    max_executions_per_day: int | None
    execution_order: int
    created_by: str | None
    updated_by: str | None
    deleted_by: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    class Config:
        from_attributes = True


class WorkflowExecutionResponse(BaseModel):
    """Workflow execution response"""

    id: str
    tenant_id: str
    workflow_id: str
    triggered_by_event_id: str | None
    triggered_by_subject_id: str | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    actions_executed: int
    actions_failed: int
    execution_log: list[dict[str, Any]] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
