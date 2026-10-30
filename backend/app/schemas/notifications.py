from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models import NotificationType, NotificationPriority


class NotificationProductRef(BaseModel):
    id: str
    name: str
    sku: str

    class Config:
        from_attributes = True


class NotificationCustomerRef(BaseModel):
    id: str
    customer_code: str
    full_name: str

    class Config:
        from_attributes = True


class NotificationOut(BaseModel):
    id: str
    type: NotificationType
    priority: NotificationPriority
    title: str
    message: str
    is_read: bool
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    product: Optional[NotificationProductRef] = None
    customer: Optional[NotificationCustomerRef] = None
    created_at: datetime
    read_at: Optional[datetime] = None
    # Only populated by the single-notification detail endpoint.
    details: Optional[dict] = None

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class MarkAllReadResponse(BaseModel):
    updated_count: int
