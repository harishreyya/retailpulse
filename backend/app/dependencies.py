from typing import List

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserStatus, UserRole
from app.security import decode_token

# tokenUrl is documentation-only here; the actual login endpoint is /auth/login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    return user


def require_roles(allowed_roles: List[UserRole]):
    """
    Dependency factory for role-based access control.
    Usage: Depends(require_roles([UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN]))
    """

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return role_checker


def get_current_company_id(current_user: User = Depends(get_current_user)) -> str:
    """
    Use this in every query that touches company-scoped data
    (products, sales, inventory, dashboards, reports, users, analytics)
    to enforce multi-tenant isolation:

        db.query(Product).filter(Product.company_id == company_id).all()

    SUPER_ADMIN is the only role intended to bypass this in cross-company
    endpoints, and only in routes explicitly designed for that purpose.
    """
    return current_user.company_id
