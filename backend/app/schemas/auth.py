from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models import UserRole, UserStatus


# ---------- Company Registration ----------

class CompanyRegisterRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=255)
    industry: Optional[str] = Field(None, max_length=255)
    company_email: EmailStr
    company_address: Optional[str] = Field(None, max_length=500)
    company_phone: Optional[str] = Field(None, max_length=50)
    owner_name: str = Field(..., min_length=2, max_length=255)
    owner_email: EmailStr
    password: str = Field(..., min_length=8)
    confirm_password: str = Field(..., min_length=8)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Password and Confirm Password must match")
        return self


class CompanyOut(BaseModel):
    id: str
    name: str
    industry: Optional[str] = None
    email: EmailStr
    address: Optional[str] = None
    phone: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Auth ----------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------- User ----------

class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: UserRole
    status: UserStatus
    last_login: Optional[datetime] = None
    created_at: datetime
    company: CompanyOut

    class Config:
        from_attributes = True


class RegisterResponse(BaseModel):
    company: CompanyOut
    user: UserOut
    tokens: TokenResponse
