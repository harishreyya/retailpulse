import json
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, AuditStatus


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _diff_only(before: Optional[dict], after: Optional[dict]) -> tuple[Optional[dict], Optional[dict]]:
    """Given full-ish before/after dicts, keep only the keys that actually
    changed — audit records should read as "what changed", not a full
    snapshot of the entity on every update."""
    if before is None or after is None:
        return before, after
    changed_keys = {k for k in after if k in before and before[k] != after[k]}
    changed_keys |= {k for k in after if k not in before}
    return (
        {k: before.get(k) for k in changed_keys},
        {k: after.get(k) for k in changed_keys},
    )


def log_action(
    db: Session,
    request: Request,
    action: str,
    company_id: Optional[str] = None,
    user_id: Optional[str] = None,
    entity_name: Optional[str] = None,
    details: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    status: AuditStatus = AuditStatus.SUCCESS,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
):
    """
    Adds the audit entry to the session but does NOT commit — it's meant to
    ride along in the same transaction as whatever operation it's logging,
    so a later failure in that operation rolls the audit entry back too
    instead of leaving an orphaned log for something that didn't happen.
    Callers are responsible for committing.

    `resource_type`/`resource_id` identify what was acted on (e.g.
    "Product", "1024"). `before`/`after` are plain dicts of just the
    old/new field values — pass the full old/new field sets and this
    trims them down to the actual diff automatically. Every value on the
    entry comes from the authenticated backend context (company_id,
    user_id, ip_address, timestamp are all set here) — never trust these
    from the request body/frontend.
    """
    before_diff, after_diff = _diff_only(before, after)
    entry = AuditLog(
        company_id=company_id,
        user_id=user_id,
        action=action,
        entity_name=entity_name,
        details=details,
        ip_address=get_client_ip(request),
        browser=request.headers.get("user-agent", "unknown"),
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        status=status,
        before_values=json.dumps(before_diff, default=str) if before_diff else None,
        after_values=json.dumps(after_diff, default=str) if after_diff else None,
    )
    db.add(entry)
    return entry
