from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DoctorSummary(BaseModel):
    id: UUID
    name: str
    specialization: str
    department: str

    model_config = ConfigDict(from_attributes=True)


class PatientResponse(BaseModel):
    id: UUID
    name: str
    phone: str
    email: str | None = None
    doctors: list[DoctorSummary] = []

    model_config = ConfigDict(from_attributes=True)