from datetime import date, time
from uuid import UUID

from pydantic import BaseModel


class AvailabilityResponse(BaseModel):
    doctor_id: UUID
    doctor_name: str
    date: date
    available_slots: list[time]