import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.organizations.models import OrgRole


class RegisterRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    is_active: bool


class MePublic(BaseModel):
    user: UserPublic
    organization_id: uuid.UUID
    role: OrgRole
