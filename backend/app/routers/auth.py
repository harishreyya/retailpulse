from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, User, UserRole, UserStatus, RefreshToken, AuditStatus
from app.schemas import (
    CompanyRegisterRequest, LoginRequest, TokenResponse,
    RefreshRequest, UserOut, RegisterResponse,
)
from app.security import (
    hash_password, verify_password, create_access_token,
    generate_refresh_token, refresh_token_expiry,
)
from app.dependencies import get_current_user
from app.audit import log_action

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(db: Session, user: User) -> TokenResponse:
    access_token = create_access_token(
        user_id=user.id, company_id=user.company_id, role=user.role.value
    )
    raw_refresh_token = generate_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token=raw_refresh_token,
        expires_at=refresh_token_expiry(),
    ))
    db.commit()
    return TokenResponse(access_token=access_token, refresh_token=raw_refresh_token)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: CompanyRegisterRequest, request: Request, db: Session = Depends(get_db)):
    if db.query(Company).filter(Company.email == payload.company_email).first():
        raise HTTPException(status_code=400, detail="A company with this email already exists")
    if db.query(User).filter(User.email == payload.owner_email).first():
        raise HTTPException(status_code=400, detail="A user with this email already exists")

    company = Company(
        name=payload.company_name,
        industry=payload.industry,
        email=payload.company_email,
        address=payload.company_address,
        phone=payload.company_phone,
    )
    db.add(company)
    db.flush()  # get company.id before creating the user

    user = User(
        company_id=company.id,
        name=payload.owner_name,
        email=payload.owner_email,
        password=hash_password(payload.password),
        role=UserRole.COMPANY_ADMIN,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(company)
    db.refresh(user)

    tokens = _issue_tokens(db, user)
    log_action(db, request, action="COMPANY_REGISTERED", company_id=company.id, user_id=user.id)
    db.commit()

    return RegisterResponse(company=company, user=user, tokens=tokens)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    invalid_credentials = HTTPException(status_code=401, detail="Invalid email or password")

    user = db.query(User).filter(User.email == payload.email).first()
    if user is None:
        # Unknown email: nothing to attribute this attempt to (no company),
        # and logging the attempted email would risk enumerating accounts
        # in the audit log itself — so this case is intentionally not logged.
        raise invalid_credentials
    if not verify_password(payload.password, user.password):
        log_action(db, request, action="LOGIN", company_id=user.company_id, user_id=user.id,
                   resource_type="Auth", status=AuditStatus.FAILED, details="Invalid password")
        db.commit()
        raise invalid_credentials
    if user.status != UserStatus.ACTIVE:
        log_action(db, request, action="LOGIN", company_id=user.company_id, user_id=user.id,
                   resource_type="Auth", status=AuditStatus.FAILED, details="Account is not active")
        db.commit()
        raise HTTPException(status_code=403, detail="Account is not active")

    tokens = _issue_tokens(db, user)
    log_action(db, request, action="LOGIN", company_id=user.company_id, user_id=user.id, resource_type="Auth")
    db.commit()
    return tokens


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    invalid_token = HTTPException(status_code=401, detail="Invalid or expired refresh token")

    stored = db.query(RefreshToken).filter(RefreshToken.token == payload.refresh_token).first()
    if stored is None or stored.revoked:
        raise invalid_token
    if stored.expires_at < __import__("datetime").datetime.utcnow():
        raise invalid_token

    user = db.query(User).filter(User.id == stored.user_id).first()
    if user is None or user.status != UserStatus.ACTIVE:
        raise invalid_token

    # Rotate: revoke the old refresh token and issue a new pair.
    stored.revoked = True
    db.commit()

    return _issue_tokens(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    stored = db.query(RefreshToken).filter(RefreshToken.token == payload.refresh_token).first()
    if stored is not None:
        stored.revoked = True
        user = db.query(User).filter(User.id == stored.user_id).first()
        if user is not None:
            log_action(db, request, action="LOGOUT", company_id=user.company_id, user_id=user.id, resource_type="Auth")
        db.commit()
    return None


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
