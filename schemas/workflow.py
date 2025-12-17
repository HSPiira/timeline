"""Pydantic schemas for workflows"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class WorkflowCreate(BaseModel):
    """Create workflow request"""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    trigger_event_type: str = Field(..., pattern=r'^[a-z0-9_]+$')
    trigger_conditions: Optional[Dict[str, Any]] = None
    actions: List[Dict[str, Any]] = Field(..., min_items=1)
    execution_order: int = Field(default=0, ge=0)
    max_executions_per_day: Optional[int] = Field(None, gt=0)
    is_active: bool = True


class WorkflowUpdate(BaseModel):
    """Update workflow request"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    trigger_conditions: Optional[Dict[str, Any]] = None
    actions: Optional[List[Dict[str, Any]]] = Field(None, min_items=1)
    execution_order: Optional[int] = Field(None, ge=0)
    max_executions_per_day: Optional[int] = Field(None, gt=0)
    is_active: Optional[bool] = None


class WorkflowResponse(BaseModel):
    """Workflow response"""
    id: str
    tenant_id: str
    name: str
    description: Optional[str]
    is_active: bool
    trigger_event_type: str
    trigger_conditions: Optional[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    max_executions_per_day: Optional[int]
    execution_order: int
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowExecutionResponse(BaseModel):
    """Workflow execution response"""
    id: str
    tenant_id: str
    workflow_id: str
    triggered_by_event_id: Optional[str]
    triggered_by_subject_id: Optional[str]
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    actions_executed: int
    actions_failed: int
    execution_log: Optional[List[Dict[str, Any]]]
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
