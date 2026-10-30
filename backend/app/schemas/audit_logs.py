from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.models import AuditStatus


class AuditLogRow(BaseModel):
    id: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    entity_name: Optional[str] = None
    description: Optional[str] = None
    ip_address: Optional[str] = None
    status: AuditStatus
    created_at: datetime


class AuditLogDetail(AuditLogRow):
    user_email: Optional[str] = None
    user_agent: Optional[str] = None
    before_values: Optional[dict] = None
    after_values: Optional[dict] = None


class AuditLogListResponse(BaseModel):
    items: list[AuditLogRow]
    total: int
    page: int
    page_size: int


class AuditLogFilterOptions(BaseModel):
    users: list[dict]  # [{"id": ..., "name": ...}]
    actions: list[str]
    resource_types: list[str]
