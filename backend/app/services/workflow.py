
from datetime import datetime
from typing import Optional
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    User,
    UserRole,
    NotificationType,
    NotificationPriority,
)
from app.models.workflow import (
    WorkflowRequest,
    WorkflowApprovalHistory,
    WorkflowConfig,
    WorkflowRequestType,
    WorkflowRequestStatus,
)
from app.models.customers import (
    Customer,
    CustomerActivity,
    CustomerActivityType,
    CustomerGender,
    CustomerType,
)
from app.services.notifications import notify_roles, notify_user
from app.audit import log_action
from app.models import (
    Inventory,
    InventoryMovement,
    Product,
    ProductStatus,
    AdjustmentType,
    AdjustmentDirection,
    MovementType,
    ImportJob,
    ImportType,
    ImportStatus,
    ImportRowStatus,
)
from app.services.inventory_utils import compute_stock_status
from app.services.notifications import evaluate_product_stock_alert
from app.services import imports as import_service
# ---------------------------------------------------------
# WORKFLOW CONSTANTS
# ---------------------------------------------------------

DEFAULT_APPROVER_ROLE = UserRole.COMPANY_ADMIN

REQUESTER_ROLES_BY_TYPE = {
    WorkflowRequestType.STOCK_ADJUSTMENT: [
        UserRole.COMPANY_ADMIN,
        UserRole.SUPER_ADMIN,
    ],
    WorkflowRequestType.PRODUCT_DEACTIVATION: [
        UserRole.COMPANY_ADMIN,
        UserRole.SUPER_ADMIN,
    ],
    WorkflowRequestType.PRODUCT_PRICE_CHANGE: [
        UserRole.COMPANY_ADMIN,
        UserRole.SUPER_ADMIN,
    ],
    WorkflowRequestType.CUSTOMER_INFORMATION_CHANGE: [
        UserRole.ANALYST,
        UserRole.COMPANY_ADMIN,
        UserRole.SUPER_ADMIN,
    ],
    WorkflowRequestType.INVENTORY_IMPORT: [
        UserRole.ANALYST,
        UserRole.COMPANY_ADMIN,
        UserRole.SUPER_ADMIN,
    ],
}

APPROVER_ROLES = [
    UserRole.COMPANY_ADMIN,
    UserRole.SUPER_ADMIN,
]


# ---------------------------------------------------------
# WORKFLOW CONFIGURATION
# ---------------------------------------------------------

def get_workflow_config(
    db: Session,
    company_id: str,
    request_type: WorkflowRequestType,
) -> Optional[WorkflowConfig]:
    """
    Fetch workflow configuration for a company and request type.
    """

    return db.query(WorkflowConfig).filter(
        WorkflowConfig.company_id == company_id,
        WorkflowConfig.request_type == request_type,
    ).first()


def get_approver_roles(
    config: Optional[WorkflowConfig],
) -> list[UserRole]:
    """
    Resolve the permitted approver roles.

    Defaults to Company Admin when no custom configuration exists.
    """

    if not config:
        return [DEFAULT_APPROVER_ROLE]

    try:
        role = UserRole(config.approver_role)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid approver role configured for this workflow.",
        )

    if role not in APPROVER_ROLES:
        raise HTTPException(
            status_code=400,
            detail="Configured role is not permitted to approve workflow requests.",
        )

    return [role]


# ---------------------------------------------------------
# APPROVAL HISTORY
# ---------------------------------------------------------

def add_workflow_history(
    db: Session,
    workflow_request: WorkflowRequest,
    actor_id: Optional[str],
    action: str,
    from_status: Optional[WorkflowRequestStatus],
    to_status: WorkflowRequestStatus,
    comments: Optional[str] = None,
) -> WorkflowApprovalHistory:
    """
    Add an entry to the workflow approval timeline.
    """

    history = WorkflowApprovalHistory(
        request_id=workflow_request.id,
        company_id=workflow_request.company_id,
        actor_id=actor_id,
        action=action,
        from_status=from_status.value if from_status else None,
        to_status=to_status.value,
        comments=comments,
    )

    db.add(history)
    return history


# ---------------------------------------------------------
# WORKFLOW AUDIT LOG
# ---------------------------------------------------------

def add_workflow_audit(
    db: Session,
    request,
    workflow_request: WorkflowRequest,
    user_id: str,
    action: str,
    details: str,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
):
    """
    Record workflow actions using the existing audit service.
    """

    log_action(
        db,
        request,
        action,
        company_id=workflow_request.company_id,
        user_id=user_id,
        entity_name=workflow_request.request_type.value,
        resource_type="WorkflowRequest",
        resource_id=workflow_request.id,
        details=details,
        before=before,
        after=after,
    )


# ---------------------------------------------------------
# NOTIFY APPROVERS
# ---------------------------------------------------------

def notify_workflow_approvers(
    db: Session,
    workflow_request: WorkflowRequest,
    title: str,
    message: str,
    notification_type: NotificationType,
):
    """
    Notify authorized approvers within the same company.
    """

    config = get_workflow_config(
        db,
        workflow_request.company_id,
        workflow_request.request_type,
    )

    roles = get_approver_roles(config)

    notify_roles(
        db,
        workflow_request.company_id,
        notification_type,
        title=title,
        message=message,
        priority=NotificationPriority.MEDIUM,
        resource_type="WorkflowRequest",
        resource_id=workflow_request.id,
        dedupe_key=(
            f"workflow:{workflow_request.id}:"
            f"{notification_type.value}"
        ),
        roles=roles,
    )


# ---------------------------------------------------------
# WORKFLOW REQUEST LOOKUP
# ---------------------------------------------------------

def get_workflow_request(
    db: Session,
    company_id: str,
    workflow_request_id: str,
) -> WorkflowRequest:
    """
    Retrieve a workflow request within the authenticated company.
    """

    workflow_request = db.query(WorkflowRequest).filter(
        WorkflowRequest.id == workflow_request_id,
        WorkflowRequest.company_id == company_id,
    ).first()

    if not workflow_request:
        raise HTTPException(
            status_code=404,
            detail="Workflow request not found.",
        )

    return workflow_request


# ---------------------------------------------------------
# STATUS VALIDATION
# ---------------------------------------------------------

ALLOWED_TRANSITIONS = {
    WorkflowRequestStatus.DRAFT: [
        WorkflowRequestStatus.SUBMITTED,
        WorkflowRequestStatus.CANCELLED,
    ],
    WorkflowRequestStatus.SUBMITTED: [
        WorkflowRequestStatus.PENDING_APPROVAL,
        WorkflowRequestStatus.CANCELLED,
    ],
    WorkflowRequestStatus.PENDING_APPROVAL: [
        WorkflowRequestStatus.APPROVED,
        WorkflowRequestStatus.REJECTED,
        WorkflowRequestStatus.CANCELLED,
    ],
    WorkflowRequestStatus.APPROVED: [],
    WorkflowRequestStatus.REJECTED: [],
    WorkflowRequestStatus.CANCELLED: [],
}


def validate_status_transition(
    current_status: WorkflowRequestStatus,
    new_status: WorkflowRequestStatus,
):
    """
    Prevent invalid workflow lifecycle transitions.
    """

    allowed = ALLOWED_TRANSITIONS.get(current_status, [])

    if new_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid workflow transition: "
                f"{current_status.value} -> {new_status.value}"
            ),
        )



# ---------------------------------------------------------
# CREATE WORKFLOW REQUEST
# ---------------------------------------------------------

def create_workflow_request(
    db: Session,
    request,
    company_id: str,
    current_user: User,
    request_type: WorkflowRequestType,
    requested_changes: dict,
    reason: str,
    related_record_type: Optional[str] = None,
    related_record_id: Optional[str] = None,
    before_values: Optional[dict] = None,
) -> WorkflowRequest:
    """
    Create a draft approval request.

    This function only stores the requested changes.
    It does not modify the underlying business record.
    """

    allowed_requester_roles = REQUESTER_ROLES_BY_TYPE.get(request_type, [])

    if current_user.role not in allowed_requester_roles:
        raise HTTPException(
            status_code=403,
            detail="You are not permitted to create workflow requests.",
        )

    if not requested_changes:
        raise HTTPException(
            status_code=400,
            detail="Requested changes cannot be empty.",
        )

    if not reason or not reason.strip():
        raise HTTPException(
            status_code=400,
            detail="A reason is required.",
        )

    config = get_workflow_config(
        db,
        company_id,
        request_type,
    )

    if config and not config.is_active:
        raise HTTPException(
            status_code=403,
            detail="This workflow is currently inactive.",
        )

    workflow_request = WorkflowRequest(
        company_id=company_id,
        request_type=request_type,
        status=WorkflowRequestStatus.DRAFT,
        requester_id=current_user.id,
        related_record_type=related_record_type,
        related_record_id=related_record_id,
        requested_changes=requested_changes,
        before_values=before_values,
        reason=reason.strip(),
        approver_role=(
            config.approver_role
            if config
            else DEFAULT_APPROVER_ROLE.value
        ),
    )

    db.add(workflow_request)
    db.flush()

    add_workflow_history(
        db=db,
        workflow_request=workflow_request,
        actor_id=current_user.id,
        action="CREATED",
        from_status=None,
        to_status=WorkflowRequestStatus.DRAFT,
        comments="Workflow request created.",
    )

    add_workflow_audit(
        db=db,
        request=request,
        workflow_request=workflow_request,
        user_id=current_user.id,
        action="Workflow Request Created",
        details=(
            f"{request_type.value} request created as a draft."
        ),
        after={
            "status": WorkflowRequestStatus.DRAFT.value,
            "request_type": request_type.value,
            "reason": reason.strip(),
        },
    )

    db.flush()

    return workflow_request


# ---------------------------------------------------------
# SUBMIT WORKFLOW REQUEST
# ---------------------------------------------------------

def submit_workflow_request(
    db: Session,
    request,
    company_id: str,
    workflow_request_id: str,
    current_user: User,
    comments: Optional[str] = None,
) -> WorkflowRequest:
    """
    Submit a draft request for approval.

    Only the original requester can submit their draft.
    """

    workflow_request = get_workflow_request(
        db,
        company_id,
        workflow_request_id,
    )

    if workflow_request.requester_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the requester can submit this request.",
        )

    if workflow_request.status != WorkflowRequestStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Only draft requests can be submitted.",
        )

    config = get_workflow_config(
        db,
        company_id,
        workflow_request.request_type,
    )

    if config and not config.is_active:
        raise HTTPException(
            status_code=403,
            detail="This workflow is currently inactive.",
        )

    # Do not silently bypass approval. Automatic execution must be
    # implemented together with the relevant business-operation handler.
    if config and not config.approval_required:
        raise HTTPException(
            status_code=409,
            detail=(
                "Approval is disabled for this workflow, but automatic "
                "execution has not yet been configured. Contact an administrator."
            ),
        )

    approver_roles = get_approver_roles(config)

    previous_status = workflow_request.status

    workflow_request.status = WorkflowRequestStatus.SUBMITTED
    workflow_request.submitted_at = datetime.utcnow()
    workflow_request.approver_role = approver_roles[0].value

    add_workflow_history(
        db=db,
        workflow_request=workflow_request,
        actor_id=current_user.id,
        action="SUBMITTED",
        from_status=previous_status,
        to_status=WorkflowRequestStatus.SUBMITTED,
        comments=comments,
    )

    # Move the submitted request into the approval queue.
    submitted_status = workflow_request.status

    workflow_request.status = WorkflowRequestStatus.PENDING_APPROVAL

    add_workflow_history(
        db=db,
        workflow_request=workflow_request,
        actor_id=current_user.id,
        action="PENDING_APPROVAL",
        from_status=submitted_status,
        to_status=WorkflowRequestStatus.PENDING_APPROVAL,
        comments="Request added to the approval queue.",
    )

    add_workflow_audit(
        db=db,
        request=request,
        workflow_request=workflow_request,
        user_id=current_user.id,
        action="Workflow Request Submitted",
        details=(
            f"{workflow_request.request_type.value} request "
            f"submitted for approval."
        ),
        before={
            "status": previous_status.value,
        },
        after={
            "status": WorkflowRequestStatus.PENDING_APPROVAL.value,
        },
    )

    notify_workflow_approvers(
        db=db,
        workflow_request=workflow_request,
        title="New Approval Request",
        message=(
            f"A {workflow_request.request_type.value.replace('_', ' ').title()} "
            f"request requires your approval."
        ),
        notification_type=NotificationType.WORKFLOW_REQUEST_SUBMITTED,
    )

    db.flush()

    return workflow_request


# ---------------------------------------------------------
# CANCEL WORKFLOW REQUEST
# ---------------------------------------------------------

def cancel_workflow_request(
    db: Session,
    request,
    company_id: str,
    workflow_request_id: str,
    current_user: User,
    comments: Optional[str] = None,
) -> WorkflowRequest:
    """
    Allow the original requester to cancel a request
    before an approval decision has been made.
    """

    workflow_request = get_workflow_request(
        db,
        company_id,
        workflow_request_id,
    )

    if workflow_request.requester_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the original requester can cancel this request.",
        )

    validate_status_transition(
        workflow_request.status,
        WorkflowRequestStatus.CANCELLED,
    )

    previous_status = workflow_request.status

    workflow_request.status = WorkflowRequestStatus.CANCELLED
    workflow_request.updated_at = datetime.utcnow()

    add_workflow_history(
        db=db,
        workflow_request=workflow_request,
        actor_id=current_user.id,
        action="CANCELLED",
        from_status=previous_status,
        to_status=WorkflowRequestStatus.CANCELLED,
        comments=comments,
    )

    add_workflow_audit(
        db=db,
        request=request,
        workflow_request=workflow_request,
        user_id=current_user.id,
        action="Workflow Request Cancelled",
        details=(
            f"{workflow_request.request_type.value} request "
            f"was cancelled by its requester."
        ),
        before={
            "status": previous_status.value,
        },
        after={
            "status": WorkflowRequestStatus.CANCELLED.value,
        },
    )

    notify_user(
        db,
        company_id,
        workflow_request.requester_id,
        NotificationType.WORKFLOW_REQUEST_CANCELLED,
        title="Approval Request Cancelled",
        message=(
            f"Your {workflow_request.request_type.value.replace('_', ' ').title()} "
            "request has been cancelled."
        ),
        priority=NotificationPriority.LOW,
        resource_type="WorkflowRequest",
        resource_id=workflow_request.id,
        dedupe_key=f"workflow-cancelled:{workflow_request.id}",
    )

    db.flush()

    return workflow_request


# ---------------------------------------------------------
# REJECT WORKFLOW REQUEST
# ---------------------------------------------------------

def reject_workflow_request(
    db: Session,
    request,
    company_id: str,
    workflow_request_id: str,
    current_user: User,
    rejection_reason: str,
) -> WorkflowRequest:
    """
    Reject a pending workflow request.

    Only an authorized approver can reject a request.
    The rejection reason is mandatory.
    """

    workflow_request = get_workflow_request(
        db,
        company_id,
        workflow_request_id,
    )

    # Only pending requests can be rejected.
    validate_status_transition(
        workflow_request.status,
        WorkflowRequestStatus.REJECTED,
    )

    # Resolve the configured approver roles.
    config = get_workflow_config(
        db,
        company_id,
        workflow_request.request_type,
    )

    approver_roles = get_approver_roles(config)

    if current_user.role not in approver_roles:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to reject this request.",
        )

    # Prevent the requester from deciding their own request.
    if workflow_request.requester_id == current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You cannot reject your own workflow request.",
        )

    if not rejection_reason or not rejection_reason.strip():
        raise HTTPException(
            status_code=400,
            detail="A rejection reason is required.",
        )

    previous_status = workflow_request.status
    now = datetime.utcnow()

    workflow_request.status = WorkflowRequestStatus.REJECTED
    workflow_request.approver_id = current_user.id
    workflow_request.rejection_reason = rejection_reason.strip()
    workflow_request.decided_at = now
    workflow_request.updated_at = now

    add_workflow_history(
        db=db,
        workflow_request=workflow_request,
        actor_id=current_user.id,
        action="REJECTED",
        from_status=previous_status,
        to_status=WorkflowRequestStatus.REJECTED,
        comments=rejection_reason.strip(),
    )

    add_workflow_audit(
        db=db,
        request=request,
        workflow_request=workflow_request,
        user_id=current_user.id,
        action="Workflow Request Rejected",
        details=(
            f"{workflow_request.request_type.value} request "
            f"was rejected. Reason: {rejection_reason.strip()}"
        ),
        before={
            "status": previous_status.value,
        },
        after={
            "status": WorkflowRequestStatus.REJECTED.value,
            "rejection_reason": rejection_reason.strip(),
            "approver_id": current_user.id,
        },
    )

    if workflow_request.requester_id:
        notify_user(
            db,
            company_id,
            workflow_request.requester_id,
            NotificationType.WORKFLOW_REQUEST_REJECTED,
            title="Approval Request Rejected",
            message=(
                f"Your {workflow_request.request_type.value.replace('_', ' ').title()} "
                f"request was rejected. Reason: {rejection_reason.strip()}"
            ),
            priority=NotificationPriority.MEDIUM,
            resource_type="WorkflowRequest",
            resource_id=workflow_request.id,
            dedupe_key=f"workflow-rejected:{workflow_request.id}",
        )

    db.flush()

    return workflow_request


# ---------------------------------------------------------
# APPLY APPROVED STOCK ADJUSTMENT
# ---------------------------------------------------------

def apply_stock_adjustment(
    db: Session,
    workflow_request: WorkflowRequest,
    approver: User,
) -> dict:
    """
    Apply an approved stock adjustment.

    Important:
    - Only called during workflow approval.
    - Locks the inventory row.
    - Checks the original stock snapshot.
    - Does not commit independently.
    """

    changes = workflow_request.requested_changes
    before = workflow_request.before_values or {}

    inventory_id = changes.get("inventory_id")
    quantity = changes.get("quantity")
    reason = changes.get("reason")
    remarks = changes.get("remarks")

    if not inventory_id:
        raise HTTPException(
            status_code=400,
            detail="Inventory ID is required for stock adjustment.",
        )

    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Adjustment quantity must be a positive integer.",
        )

    if not reason or not str(reason).strip():
        raise HTTPException(
            status_code=400,
            detail="Adjustment reason is required.",
        )

    # Lock the company-scoped inventory row to prevent concurrent updates.
    inventory = db.query(Inventory).filter(
        Inventory.id == inventory_id,
        Inventory.company_id == workflow_request.company_id,
    ).with_for_update().first()

    if not inventory:
        raise HTTPException(
            status_code=404,
            detail="Inventory record not found.",
        )

    product = db.query(Product).filter(
        Product.id == inventory.product_id,
        Product.company_id == workflow_request.company_id,
    ).with_for_update().first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Related product not found.",
        )

    # Reject stale requests if stock changed after submission.
    current_values = {
        "current_stock": inventory.current_stock,
        "available_stock": inventory.available_stock,
        "reserved_stock": inventory.reserved_stock,
        "reorder_level": inventory.reorder_level,
        "product_stock_quantity": product.stock_quantity,
    }

    for field, expected_value in before.items():
        if field in current_values and current_values[field] != expected_value:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Inventory has changed since this request was submitted. "
                    f"Field '{field}' no longer matches the original values. "
                    "Please create a new request."
                ),
            )

    try:
        adjustment_type = AdjustmentType(
            changes.get("adjustment_type")
        )
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail="Invalid stock adjustment type.",
        )

    if adjustment_type == AdjustmentType.STOCK_IN:
        movement_type = MovementType.STOCK_ADDITION
        delta = quantity

    elif adjustment_type == AdjustmentType.STOCK_OUT:
        movement_type = MovementType.STOCK_REMOVAL
        delta = -quantity

    elif adjustment_type == AdjustmentType.MANUAL_ADJUSTMENT:
        try:
            direction = AdjustmentDirection(
                changes.get("direction")
            )
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail="A valid direction is required for manual adjustment.",
            )

        movement_type = MovementType.MANUAL_ADJUSTMENT
        delta = (
            quantity
            if direction == AdjustmentDirection.INCREASE
            else -quantity
        )

    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported stock adjustment type.",
        )

    if delta < 0 and abs(delta) > inventory.available_stock:
        raise HTTPException(
            status_code=400,
            detail="Stock reduction cannot exceed available stock.",
        )

    previous_quantity = inventory.current_stock
    new_quantity = previous_quantity + delta

    if new_quantity < 0:
        raise HTTPException(
            status_code=400,
            detail="Stock quantity cannot become negative.",
        )

    previous_status = inventory.stock_status

    # Apply the approved changes.
    inventory.current_stock = new_quantity
    inventory.available_stock = max(
        0,
        new_quantity - inventory.reserved_stock,
    )
    inventory.stock_status = compute_stock_status(
        inventory.available_stock,
        inventory.reorder_level,
    )

    product.stock_quantity = new_quantity

    movement = InventoryMovement(
        inventory_id=inventory.id,
        movement_type=movement_type,
        quantity_changed=delta,
        previous_quantity=previous_quantity,
        updated_quantity=new_quantity,
        reason=str(reason).strip(),
        remarks=remarks,
        performed_by=approver.id,
    )

    db.add(movement)
    db.flush()

    # Preserve existing inventory alert behaviour.
    if inventory.stock_status != previous_status:
        evaluate_product_stock_alert(
            db,
            workflow_request.company_id,
            inventory,
            product,
        )

    return {
        "inventory_id": inventory.id,
        "product_id": product.id,
        "previous_stock": previous_quantity,
        "updated_stock": new_quantity,
        "quantity_changed": delta,
        "movement_type": movement_type.value,
        "stock_status": inventory.stock_status.value,
    }

def apply_product_deactivation(db: Session, workflow_request: WorkflowRequest, approver: User):
    changes = workflow_request.requested_changes or {}
    before = workflow_request.before_values or {}

    product_id = workflow_request.related_record_id

    if not product_id:
        raise HTTPException(status_code=400, detail="Product ID is missing.")

    product = (
        db.query(Product)
        .filter(
            Product.id == product_id,
            Product.company_id == workflow_request.company_id,
        )
        .with_for_update()
        .first()
    )

    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    expected_status = before.get("status")

    if expected_status is not None and product.status.value != expected_status:
        raise HTTPException(
            status_code=409,
            detail="Product status changed after this request was submitted. Please create a new request.",
        )

    if product.status == ProductStatus.INACTIVE:
        raise HTTPException(
            status_code=409,
            detail="Product is already inactive.",
        )

    previous_status = product.status.value

    product.status = ProductStatus.INACTIVE

    db.flush()

    return {
        "product_id": str(product.id),
        "previous_status": previous_status,
        "updated_status": product.status.value,
    }
    
def apply_product_price_change(
      db: Session,
      workflow_request: WorkflowRequest,
      approver: User,
    ):
    changes = workflow_request.requested_changes or {}
    before = workflow_request.before_values or {}

    product_id = workflow_request.related_record_id

    if not product_id:
        raise HTTPException(status_code=400, detail="Product ID is missing.")

    product = (
        db.query(Product)
        .filter(
            Product.id == product_id,
            Product.company_id == workflow_request.company_id,
        )
        .with_for_update()
        .first()
    )

    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    price_fields = ("unit_price", "cost_price")
    new_prices = {}

    for field in price_fields:
        if field not in changes:
            continue

        try:
            new_value = Decimal(str(changes[field]))
        except (InvalidOperation, TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid {field} value.",
            )

        if not new_value.is_finite() or new_value < 0:
            raise HTTPException(
                status_code=400,
                detail=f"{field} must be a valid non-negative number.",
            )

        new_prices[field] = new_value

    if not new_prices:
        raise HTTPException(
            status_code=400,
            detail="At least one price field must be provided.",
        )

    current_prices = {
        "unit_price": product.unit_price,
        "cost_price": product.cost_price,
    }

    # Detect changes made after the approval request was submitted.
    for field in price_fields:
        if field in before:
            try:
                expected = Decimal(str(before[field]))
                current = Decimal(str(current_prices[field]))
            except (InvalidOperation, TypeError, ValueError):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid snapshot value for {field}.",
                )

            if current != expected:
                raise HTTPException(
                    status_code=409,
                    detail=f"Product {field} changed after this request was submitted. Please create a new request.",
                )

    final_unit_price = new_prices.get(
        "unit_price", Decimal(str(product.unit_price))
    )
    final_cost_price = new_prices.get(
        "cost_price", Decimal(str(product.cost_price))
    )

    if final_cost_price > final_unit_price:
        raise HTTPException(
            status_code=400,
            detail="Cost price cannot exceed unit price.",
        )

    previous_values = {
        field: str(current_prices[field])
        for field in price_fields
    }

    if "unit_price" in new_prices:
        product.unit_price = new_prices["unit_price"]

    if "cost_price" in new_prices:
        product.cost_price = new_prices["cost_price"]

    db.flush()

    updated_values = {
        field: str(getattr(product, field))
        for field in price_fields
    }

    return {
        "product_id": str(product.id),
        "previous_values": previous_values,
        "updated_values": updated_values,
    }


def apply_customer_information_change(
    db: Session,
    workflow_request: WorkflowRequest,
    approver: User,
) -> dict:
    changes = workflow_request.requested_changes or {}
    before = workflow_request.before_values or {}

    customer_id = workflow_request.related_record_id

    if not customer_id:
        raise HTTPException(
            status_code=400,
            detail="Customer ID is missing.",
        )

    customer = (
        db.query(Customer)
        .filter(
            Customer.id == customer_id,
            Customer.company_id == workflow_request.company_id,
            Customer.is_deleted.is_(False),
        )
        .with_for_update()
        .first()
    )

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

    if not changes:
        raise HTTPException(
            status_code=400,
            detail="No customer changes were provided.",
        )

    invalid_fields = set(changes.keys()) - allowed_fields

    if invalid_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported customer fields: {', '.join(sorted(invalid_fields))}",
        )

    # Check that the customer has not changed since submission.
    for field, expected_value in before.items():
        if field not in allowed_fields:
            continue

        current_value = getattr(customer, field)

        if hasattr(current_value, "value"):
            current_value = current_value.value
        elif hasattr(current_value, "isoformat"):
            current_value = current_value.isoformat()

        if current_value != expected_value:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Customer field '{field}' changed after this request "
                    "was submitted. Please create a new request."
                ),
            )

    # Normalize and validate incoming values.
    normalized_changes = dict(changes)

    for field in ("first_name", "last_name", "email", "phone"):
        if field in normalized_changes:
            value = normalized_changes[field]

            if not isinstance(value, str) or not value.strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"{field} cannot be empty.",
                )

            normalized_changes[field] = value.strip()

    if "email" in normalized_changes:
        duplicate = db.query(Customer).filter(
            Customer.company_id == workflow_request.company_id,
            Customer.email == normalized_changes["email"],
            Customer.id != customer.id,
            Customer.is_deleted.is_(False),
        ).first()

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="Another customer already uses this email address.",
            )

    if "phone" in normalized_changes:
        duplicate = db.query(Customer).filter(
            Customer.company_id == workflow_request.company_id,
            Customer.phone == normalized_changes["phone"],
            Customer.id != customer.id,
            Customer.is_deleted.is_(False),
        ).first()

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="Another customer already uses this phone number.",
            )

    if "gender" in normalized_changes:
        try:
            normalized_changes["gender"] = CustomerGender(
                normalized_changes["gender"]
            )
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail="Invalid customer gender.",
            )

    if "customer_type" in normalized_changes:
        try:
            normalized_changes["customer_type"] = CustomerType(
                normalized_changes["customer_type"]
            )
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail="Invalid customer type.",
            )

    # Capture previous values for the approval result.
    previous_values = {}

    for field in normalized_changes:
        value = getattr(customer, field)

        if hasattr(value, "value"):
            value = value.value
        elif hasattr(value, "isoformat"):
            value = value.isoformat()

        previous_values[field] = value

    # Apply approved changes.
    for field, value in normalized_changes.items():
        setattr(customer, field, value)

    if "first_name" in normalized_changes or "last_name" in normalized_changes:
        customer.full_name = (
            f"{customer.first_name} {customer.last_name}"
        ).strip()

    db.flush()

    updated_values = {}

    for field in normalized_changes:
        value = getattr(customer, field)

        if hasattr(value, "value"):
            value = value.value
        elif hasattr(value, "isoformat"):
            value = value.isoformat()

        updated_values[field] = value

    if "first_name" in normalized_changes or "last_name" in normalized_changes:
        updated_values["full_name"] = customer.full_name

    activity = CustomerActivity(
        customer_id=customer.id,
        company_id=workflow_request.company_id,
        activity_type=CustomerActivityType.PROFILE_UPDATED,
        description=(
            "Customer profile updated through an approved workflow request. "
            f"Approved by user {approver.id}."
        ),
    )

    db.add(activity)
    db.flush()

    return {
        "customer_id": str(customer.id),
        "previous_values": previous_values,
        "updated_values": updated_values,
    }

def validate_inventory_import_for_approval(
    db: Session,
    workflow_request: WorkflowRequest,
) -> ImportJob:
    """Revalidate an inventory import before approving its workflow request."""

    if workflow_request.related_record_type != "IMPORT_JOB":
        raise HTTPException(
            status_code=400,
            detail="Invalid related record type for inventory import approval.",
        )

    job = (
        db.query(ImportJob)
        .filter(
            ImportJob.id == workflow_request.related_record_id,
            ImportJob.company_id == workflow_request.company_id,
        )
        .with_for_update()
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Inventory import job not found.",
        )

    if job.import_type != ImportType.INVENTORY:
        raise HTTPException(
            status_code=400,
            detail="The linked import job is not an inventory import.",
        )

    if job.status != ImportStatus.VALIDATED:
        raise HTTPException(
            status_code=409,
            detail="Only validated inventory imports can be approved.",
        )

    requested = workflow_request.requested_changes or {}

    expected_values = {
        "import_id": str(job.id),
        "filename": job.filename,
        "total_records": job.total_records,
        "valid_records": job.valid_records,
        "invalid_records": job.invalid_records,
        "duplicate_records": job.duplicate_records,
    }

    for key, actual_value in expected_values.items():
        if requested.get(key) != actual_value:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Inventory import details changed since submission: {key}. "
                    "Please submit a new approval request."
                ),
            )

    # Revalidate the original CSV against current company inventory data.
    parsed = import_service.parse_csv_text(job.raw_content)

    results = import_service.validate_rows(
        db,
        workflow_request.company_id,
        ImportType.INVENTORY,
        parsed,
    )

    current_counts = {
        "total_records": len(results),
        "valid_records": sum(1 for row in results if row.status is None),
        "invalid_records": sum(
            1 for row in results
            if row.status == ImportRowStatus.INVALID
        ),
        "duplicate_records": sum(
            1 for row in results
            if row.status == ImportRowStatus.DUPLICATE
        ),
    }

    for key, current_value in current_counts.items():
        if requested.get(key) != current_value:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Inventory data has changed since this import was submitted. "
                    "Please upload and submit the CSV again."
                ),
            )

    if current_counts["valid_records"] == 0:
        raise HTTPException(
            status_code=400,
            detail="The inventory import contains no valid records.",
        )

    return job

def approve_workflow_request(
    db: Session,
    request,
    company_id: str,
    workflow_request_id: str,
    current_user: User,
    comments: Optional[str] = None,
) -> WorkflowRequest:
    """
    Approve a pending workflow request and apply its business changes.

    Business updates, approval history, audit logs and notifications
    are added to the same database transaction.
    """

    workflow_request = (
        db.query(WorkflowRequest)
        .filter(
            WorkflowRequest.id == workflow_request_id,
            WorkflowRequest.company_id == company_id,
        )
        .with_for_update()
        .first()
    )

    if not workflow_request:
        raise HTTPException(
            status_code=404,
            detail="Workflow request not found.",
        )

    validate_status_transition(
        workflow_request.status,
        WorkflowRequestStatus.APPROVED,
    )

    config = get_workflow_config(
        db,
        company_id,
        workflow_request.request_type,
    )

    if config and not config.is_active:
        raise HTTPException(
            status_code=403,
            detail="This workflow is currently inactive.",
        )

    approver_roles = get_approver_roles(config)

    if current_user.role not in approver_roles:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to approve this request.",
        )

    if workflow_request.requester_id == current_user.id:
        allow_self_approval = bool(
            config and config.allow_self_approval
        )

        if not allow_self_approval:
            raise HTTPException(
                status_code=403,
                detail="You cannot approve your own workflow request.",
            )

    # Execute the correct business operation.
    if workflow_request.request_type == WorkflowRequestType.STOCK_ADJUSTMENT:
        result = apply_stock_adjustment(
            db,
            workflow_request,
            current_user,
        )

    elif workflow_request.request_type == WorkflowRequestType.PRODUCT_DEACTIVATION:
        result = apply_product_deactivation(
            db,
            workflow_request,
            current_user,
        )

    elif workflow_request.request_type == WorkflowRequestType.PRODUCT_PRICE_CHANGE:
        result = apply_product_price_change(
            db,
            workflow_request,
            current_user,
        )

    elif workflow_request.request_type == WorkflowRequestType.CUSTOMER_INFORMATION_CHANGE:
        result = apply_customer_information_change(
            db,
            workflow_request,
            current_user,
        )

    elif workflow_request.request_type == WorkflowRequestType.INVENTORY_IMPORT:
       result = validate_inventory_import_for_approval(
        db,
        workflow_request,
    )

    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported workflow request type.",
        )

    previous_status = workflow_request.status
    now = datetime.utcnow()

    workflow_request.status = WorkflowRequestStatus.APPROVED
    workflow_request.approver_id = current_user.id
    workflow_request.decided_at = now
    workflow_request.updated_at = now

    add_workflow_history(
        db=db,
        workflow_request=workflow_request,
        actor_id=current_user.id,
        action="APPROVED",
        from_status=previous_status,
        to_status=WorkflowRequestStatus.APPROVED,
        comments=comments,
    )

    add_workflow_audit(
        db=db,
        request=request,
        workflow_request=workflow_request,
        user_id=current_user.id,
        action="Workflow Request Approved",
        details=(
            f"{workflow_request.request_type.value} request approved."
        ),
        before={
            "status": previous_status.value,
        },
        after={
            "status": WorkflowRequestStatus.APPROVED.value,
            "approver_id": current_user.id,
            "business_changes": result,
        },
    )

    if workflow_request.requester_id:
        notify_user(
            db,
            company_id,
            workflow_request.requester_id,
            NotificationType.WORKFLOW_REQUEST_APPROVED,
            title="Approval Request Approved",
            message=(
                f"Your {workflow_request.request_type.value.replace('_', ' ').title()} "
                "request has been approved."
            ),
            priority=NotificationPriority.MEDIUM,
            resource_type="WorkflowRequest",
            resource_id=workflow_request.id,
            dedupe_key=f"workflow-approved:{workflow_request.id}",
        )

    db.flush()

    return workflow_request
