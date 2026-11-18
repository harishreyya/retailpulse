
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

from app.models.workflow import (
    WorkflowRequestType,
    WorkflowRequestStatus,
)


# ---------- Create workflow request ----------

class WorkflowRequestCreate(BaseModel):
    request_type: WorkflowRequestType

    related_record_type: Optional[str] = Field(
        None, max_length=50
    )
    related_record_id: Optional[str] = None

    requested_changes: dict = Field(
        ..., min_length=1
    )

    reason: str = Field(
        ..., min_length=5, max_length=2000
    )


# ---------- Workflow actions ----------

class WorkflowSubmitRequest(BaseModel):
    comments: Optional[str] = Field(
        None, max_length=1000
    )


class WorkflowApproveRequest(BaseModel):
    comments: Optional[str] = Field(
        None, max_length=1000
    )


class WorkflowRejectRequest(BaseModel):
    rejection_reason: str = Field(
        ..., min_length=5, max_length=2000
    )


class WorkflowCancelRequest(BaseModel):
    comments: Optional[str] = Field(
        None, max_length=1000
    )


# ---------- Approval history ----------

class WorkflowHistoryOut(BaseModel):
    id: str
    actor_id: Optional[str] = None
    action: str
    from_status: Optional[str] = None
    to_status: str
    comments: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# ---------- Workflow request response ----------

class WorkflowRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    request_type: WorkflowRequestType
    status: WorkflowRequestStatus

    requester_id: Optional[str] = None
    approver_id: Optional[str] = None
    approver_role: Optional[str] = None

    related_record_type: Optional[str] = None
    related_record_id: Optional[str] = None

    requested_changes: dict
    before_values: Optional[dict] = None

    reason: str
    rejection_reason: Optional[str] = None

    submitted_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime

    history: list[WorkflowHistoryOut] = []


class WorkflowRequestListResponse(BaseModel):
    items: list[WorkflowRequestOut]
    total: int
    page: int
    page_size: int


# ---------- Pending approval summary ----------

class WorkflowPendingCountOut(BaseModel):
    total_pending: int
    by_request_type: dict[str, int]


# ---------- Workflow configuration ----------

class WorkflowConfigCreate(BaseModel):
    request_type: WorkflowRequestType

    approver_role: str = Field(
        default="COMPANY_ADMIN",
        pattern="^(COMPANY_ADMIN|SUPER_ADMIN)$",
    )

    approval_required: bool = True
    is_active: bool = True

    # Self-approval is disabled by default.
    allow_self_approval: bool = False


class WorkflowConfigUpdate(BaseModel):
    approver_role: Optional[str] = Field(
        None,
        pattern="^(COMPANY_ADMIN|SUPER_ADMIN)$",
    )

    approval_required: Optional[bool] = None
    is_active: Optional[bool] = None
    allow_self_approval: Optional[bool] = None


class WorkflowConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    request_type: WorkflowRequestType
    approver_role: str
    approval_required: bool
    is_active: bool
    allow_self_approval: bool
    created_at: datetime
    updated_at: datetime


class WorkflowConfigListResponse(BaseModel):
    items: list[WorkflowConfigOut]
    total: int
