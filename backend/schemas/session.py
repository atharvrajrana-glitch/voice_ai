from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    phone: str


class PatientSignUp(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    phone: str = Field(min_length=5, max_length=20)
    email: str | None = Field(default=None, max_length=255)


class SessionResponse(BaseModel):
    session_id: UUID
    expires_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
