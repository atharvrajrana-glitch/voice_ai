from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DoctorResponse(BaseModel):
    id: UUID
    name: str
    specialization: str
    department: str

    model_config = ConfigDict(from_attributes=True)


class DoctorListResponse(BaseModel):
    doctors: list[DoctorResponse]