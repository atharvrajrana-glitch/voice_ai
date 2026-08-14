from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AppointmentCreate(BaseModel):
    doctor_id: UUID
    appointment_date: date
    appointment_time: time


class AppointmentDoctorResponse(BaseModel):
    id: UUID
    name: str
    specialization: str
    department: str

    model_config = ConfigDict(from_attributes=True)


class AppointmentResponse(BaseModel):
    id: UUID
    doctor: AppointmentDoctorResponse
    appointment_date: date
    appointment_time: time
    status: str

    model_config = ConfigDict(from_attributes=True)


class AppointmentListResponse(BaseModel):
    appointments: list[AppointmentResponse]