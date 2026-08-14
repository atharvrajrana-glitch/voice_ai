from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SessionCreate(BaseModel):
    phone: str


class SessionResponse(BaseModel):
    session_id: UUID
    expires_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)