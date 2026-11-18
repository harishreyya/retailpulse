
from typing import Optional
from sqlalchemy import cast, String
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import cast, String, func

from app.database import get_db
from decimal import Decimal

from app.models import (
    Inventory,
    Product,
    ProductStatus,
)
from app.models.customers import Customer
from app.dependencies import (
    get_current_user,
    get_current_company_id,
    require_roles,
)
from app.models import User, UserRole
from app.models.workflow import (
    WorkflowRequest,
    WorkflowRequestType,
    WorkflowRequestStatus,
    WorkflowApprovalHistory,
    WorkflowConfig,
)
from app.schemas.workflow import (
    WorkflowRequestCreate,
    WorkflowSubmitRequest,
    WorkflowApproveRequest,
    WorkflowRejectRequest,
    WorkflowCancelRequest,
    WorkflowRequestOut,
    WorkflowRequestListResponse,
    WorkflowPendingCountOut,
    WorkflowConfigCreate,
    WorkflowConfigUpdate,
    WorkflowConfigOut,
    WorkflowConfigListResponse,
    WorkflowHistoryOut,
)
from app.services import workflow as workflow_service

router = APIRouter(
    prefix="/workflow",
    tags=["workflow-approval"],
)

ADMIN_ROLES = [
    UserRole.COMPANY_ADMIN,
    UserRole.SUPER_ADMIN,
]


def _serialize_snapshot_value(value):
    if value is None:
        return None

    if hasattr(value, "value"):
        return value.value

    if hasattr(value, "isoformat"):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    return value


def _capture_before_values(
    db: Session,
    company_id: str,
    payload: WorkflowRequestCreate,
) -> dict:
    request_type = payload.request_type
    changes = payload.requested_changes or {}

    # Stock adjustment snapshot
    if request_type == WorkflowRequestType.STOCK_ADJUSTMENT:
        inventory_id = changes.get("inventory_id")

        if not inventory_id:
            raise HTTPException(
                status_code=400,
                detail="inventory_id is required.",
            )

        inventory = db.query(Inventory).filter(
            Inventory.id == inventory_id,
            Inventory.company_id == company_id,
        ).first()

        if not inventory:
            raise HTTPException(
                status_code=404,
                detail="Inventory record not found.",
            )

        product = db.query(Product).filter(
            Product.id == inventory.product_id,
            Product.company_id == company_id,
        ).first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Related product not found.",
            )

        return {
            "current_stock": inventory.current_stock,
            "available_stock": inventory.available_stock,
            "reserved_stock": inventory.reserved_stock,
            "reorder_level": inventory.reorder_level,
            "product_stock_quantity": product.stock_quantity,
        }

    # Product deactivation snapshot
    if request_type == WorkflowRequestType.PRODUCT_DEACTIVATION:
        if not payload.related_record_id:
            raise HTTPException(
                status_code=400,
                detail="Product ID is required.",
            )

        product = db.query(Product).filter(
            Product.id == payload.related_record_id,
            Product.company_id == company_id,
        ).first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found.",
            )

        return {
            "status": _serialize_snapshot_value(product.status),
        }

    # Product price change snapshot
    if request_type == WorkflowRequestType.PRODUCT_PRICE_CHANGE:
        if not payload.related_record_id:
            raise HTTPException(
                status_code=400,
                detail="Product ID is required.",
            )

        product = db.query(Product).filter(
            Product.id == payload.related_record_id,
            Product.company_id == company_id,
        ).first()

        if not product:
            raise HTTPException(
                status_code=404,
                detail="Product not found.",
            )

        return {
            "unit_price": str(product.unit_price),
            "cost_price": str(product.cost_price),
        }

    # Customer information change snapshot
    if request_type == WorkflowRequestType.CUSTOMER_INFORMATION_CHANGE:
        if not payload.related_record_id:
            raise HTTPException(
                status_code=400,
                detail="Customer ID is required.",
            )

        customer = db.query(Customer).filter(
            Customer.id == payload.related_record_id,
            Customer.company_id == company_id,
            Customer.is_deleted.is_(False),
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer not found.",
            )

        allowed_fields = {
            "first_name",
            "last_name",
            "email",
            "phone",
            "date_of_birth",
            "gender",
            "address",
            "city",
            "state",
            "country",
            "postal_code",
            "customer_type",
            "preferred_channel",
        }

        invalid_fields = set(changes) - allowed_fields

        if invalid_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported customer fields: {', '.join(sorted(invalid_fields))}",
            )

        return {
            field: _serialize_snapshot_value(getattr(customer, field))
            for field in changes
        }

    if request_type == WorkflowRequestType.INVENTORY_IMPORT:
        raise HTTPException(
            status_code=501,
            detail="Inventory import workflow integration is not ready yet.",
        )

    raise HTTPException(
        status_code=400,
        detail="Unsupported workflow request type.",
    )


@router.post(
    "/requests",
    response_model=WorkflowRequestOut,
    status_code=201,
)
def create_workflow_request(
    payload: WorkflowRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    try:
        before_values = _capture_before_values(
            db,
            company_id,
            payload,
        )

        workflow_request = workflow_service.create_workflow_request(
            db=db,
            request=request,
            company_id=company_id,
            current_user=current_user,
            request_type=payload.request_type,
            requested_changes=payload.requested_changes,
            reason=payload.reason,
            related_record_type=payload.related_record_type,
            related_record_id=payload.related_record_id,
            before_values=before_values,
        )

        db.commit()
        db.refresh(workflow_request)

        return workflow_request

    except Exception:
        db.rollback()
        raise


@router.post(
    "/requests/{workflow_request_id}/submit",
    response_model=WorkflowRequestOut,
)
def submit_workflow_request(
    workflow_request_id: str,
    payload: WorkflowSubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    try:
        workflow_request = workflow_service.submit_workflow_request(
            db=db,
            request=request,
            company_id=company_id,
            workflow_request_id=workflow_request_id,
            current_user=current_user,
            comments=payload.comments,
        )

        db.commit()
        db.refresh(workflow_request)

        return workflow_request

    except Exception:
        db.rollback()
        raise


@router.get(
    "/requests",
    response_model=WorkflowRequestListResponse,
)
def list_workflow_requests(
    request_type: Optional[WorkflowRequestType] = None,
    status: Optional[WorkflowRequestStatus] = None,
    search: Optional[str] = Query(None, min_length=1, max_length=100),
    requester_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    query = db.query(WorkflowRequest).filter(
        WorkflowRequest.company_id == company_id
    )

    # Non-admin users can see only their own requests.
    # Non-admin users can only see their own requests.
    if current_user.role not in ADMIN_ROLES:
        query = query.filter(
            WorkflowRequest.requester_id == current_user.id
         )

    # Admins can optionally filter requests by requester.
    elif requester_id:
        query = query.filter(
            WorkflowRequest.requester_id == requester_id
    )

    if request_type:
        query = query.filter(
            WorkflowRequest.request_type == request_type
        )

    if status:
        query = query.filter(
            WorkflowRequest.status == status
        )

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            WorkflowRequest.reason.ilike(term)
            | cast(WorkflowRequest.id, String).ilike(term)
            | cast(WorkflowRequest.related_record_id, String).ilike(term)
        )

    total = query.count()

    requests = (
        query
        .order_by(WorkflowRequest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    request_ids = [item.id for item in requests]

    histories = []

    if request_ids:
        histories = (
            db.query(WorkflowApprovalHistory)
            .filter(
                WorkflowApprovalHistory.company_id == company_id,
                WorkflowApprovalHistory.request_id.in_(request_ids),
            )
            .order_by(WorkflowApprovalHistory.created_at.asc())
            .all()
        )

    history_by_request = {}

    for history in histories:
        history_by_request.setdefault(history.request_id, []).append(
            history
        )

    items = []

    for item in requests:
        response_item = WorkflowRequestOut.model_validate(item)

        response_item.history = [
            WorkflowHistoryOut.model_validate(history)
            for history in history_by_request.get(item.id, [])
        ]

        items.append(response_item)

    return WorkflowRequestListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )

@router.get("/requests/{workflow_request_id}", response_model=WorkflowRequestOut)
def get_workflow_request_details(
    workflow_request_id: str,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    workflow_request = workflow_service.get_workflow_request(
        db=db,
        company_id=company_id,
        workflow_request_id=workflow_request_id,
    )

    # Non-admin users can only view their own requests.
    if (
        current_user.role not in ADMIN_ROLES
        and workflow_request.requester_id != current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to view this workflow request.",
        )

    history_records = (
        db.query(WorkflowApprovalHistory)
        .filter(
            WorkflowApprovalHistory.request_id == workflow_request.id,
            WorkflowApprovalHistory.company_id == company_id,
        )
        .order_by(WorkflowApprovalHistory.created_at.asc())
        .all()
    )

    response = WorkflowRequestOut.model_validate(workflow_request)
    response.history = [
        WorkflowHistoryOut.model_validate(record)
        for record in history_records
    ]

    return response

@router.post(
    "/requests/{workflow_request_id}/approve",
    response_model=WorkflowRequestOut,
)
def approve_workflow_request(
    workflow_request_id: str,
    payload: WorkflowApproveRequest,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    try:
        workflow_request = workflow_service.approve_workflow_request(
            db=db,
            request=request,
            company_id=company_id,
            workflow_request_id=workflow_request_id,
            current_user=current_user,
            comments=payload.comments,
        )

        db.commit()
        db.refresh(workflow_request)

        return workflow_request

    except Exception:
        db.rollback()
        raise

@router.post(
    "/requests/{workflow_request_id}/reject",
    response_model=WorkflowRequestOut,
)
def reject_workflow_request(
    workflow_request_id: str,
    payload: WorkflowRejectRequest,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    try:
        workflow_request = workflow_service.reject_workflow_request(
            db=db,
            request=request,
            company_id=company_id,
            workflow_request_id=workflow_request_id,
            current_user=current_user,
            rejection_reason=payload.rejection_reason,
        )

        db.commit()
        db.refresh(workflow_request)

        return workflow_request

    except Exception:
        db.rollback()
        raise

@router.post(
    "/requests/{workflow_request_id}/cancel",
    response_model=WorkflowRequestOut,
)
def cancel_workflow_request(
    workflow_request_id: str,
    payload: WorkflowCancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(get_current_user),
):
    try:
        workflow_request = workflow_service.cancel_workflow_request(
            db=db,
            request=request,
            company_id=company_id,
            workflow_request_id=workflow_request_id,
            current_user=current_user,
            comments=payload.comments,
        )

        db.commit()
        db.refresh(workflow_request)

        return workflow_request

    except Exception:
        db.rollback()
        raise

@router.get(
    "/pending-counts",
    response_model=WorkflowPendingCountOut,
)
def get_pending_approval_counts(
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(
        require_roles(ADMIN_ROLES)
    ),
):
    results = (
        db.query(
            WorkflowRequest.request_type,
            func.count(WorkflowRequest.id).label("total"),
        )
        .filter(
            WorkflowRequest.company_id == company_id,
            WorkflowRequest.status == WorkflowRequestStatus.PENDING_APPROVAL,
        )
        .group_by(WorkflowRequest.request_type)
        .all()
    )

    by_request_type = {
        request_type.value: count
        for request_type, count in results
    }

    total_pending = sum(by_request_type.values())

    return WorkflowPendingCountOut(
        total_pending=total_pending,
        by_request_type=by_request_type,
    )

@router.get(
    "/configs",
    response_model=WorkflowConfigListResponse,
)
def get_workflow_configs(
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(
        require_roles(ADMIN_ROLES)
    ),
):
    configs = (
        db.query(WorkflowConfig)
        .filter(WorkflowConfig.company_id == company_id)
        .order_by(WorkflowConfig.created_at.asc())
        .all()
    )

    return WorkflowConfigListResponse(
        items=[
            WorkflowConfigOut.model_validate(config)
            for config in configs
        ],
        total=len(configs),
    )

@router.post(
    "/configs",
    response_model=WorkflowConfigOut,
    status_code=201,
)
def create_workflow_config(
    payload: WorkflowConfigCreate,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(
        require_roles(ADMIN_ROLES)
    ),
):
    try:
        # Prevent duplicate configuration for the same request type.
        existing_config = (
            db.query(WorkflowConfig)
            .filter(
                WorkflowConfig.company_id == company_id,
                WorkflowConfig.request_type == payload.request_type,
            )
            .first()
        )

        if existing_config:
            raise HTTPException(
                status_code=409,
                detail="Workflow configuration already exists for this request type.",
            )

        # Self-approval is disabled by policy.
        if payload.allow_self_approval:
            raise HTTPException(
                status_code=400,
                detail="Self-approval is not permitted.",
            )

        config = WorkflowConfig(
            company_id=company_id,
            request_type=payload.request_type,
            approver_role=payload.approver_role,
            approval_required=payload.approval_required,
            is_active=payload.is_active,
            allow_self_approval=False,
        )

        db.add(config)
        db.commit()
        db.refresh(config)

        return config

    except Exception:
        db.rollback()
        raise

@router.patch(
    "/configs/{config_id}",
    response_model=WorkflowConfigOut,
)
def update_workflow_config(
    config_id: str,
    payload: WorkflowConfigUpdate,
    db: Session = Depends(get_db),
    company_id: str = Depends(get_current_company_id),
    current_user: User = Depends(
        require_roles(ADMIN_ROLES)
    ),
):
    try:
        config = (
            db.query(WorkflowConfig)
            .filter(
                WorkflowConfig.id == config_id,
                WorkflowConfig.company_id == company_id,
            )
            .first()
        )

        if not config:
            raise HTTPException(
                status_code=404,
                detail="Workflow configuration not found.",
            )

        updates = payload.model_dump(exclude_unset=True)

        # Self-approval is not permitted.
        if updates.get("allow_self_approval") is True:
            raise HTTPException(
                status_code=400,
                detail="Self-approval is not permitted.",
            )

        for field, value in updates.items():
            setattr(config, field, value)

        config.allow_self_approval = False

        db.commit()
        db.refresh(config)

        return config

    except Exception:
        db.rollback()
        raise