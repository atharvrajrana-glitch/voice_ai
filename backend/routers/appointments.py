from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from ai_core.service import get_current_session
from app.models.patient_session import PatientSession
from schemas.appointment import (
    AppointmentListResponse,
    AppointmentResponse,
    AppointmentCreate,
    AppointmentResponse,
)
from ai_core.service import (
    get_patient_appointments,
    get_upcoming_patient_appointment,
)
from schemas.availability import AvailabilityResponse
from ai_core.availability_service import get_doctor_availability ,create_appointment


router = APIRouter(
    prefix="/api/v1/appointments",
    tags=["Appointments"],
)


@router.get(
    "",
    response_model=AppointmentListResponse,
)
async def get_appointments(
    session: PatientSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    appointments = await get_patient_appointments(
        patient_id=session.patient_id,
        db=db,
    )

    return AppointmentListResponse(
        appointments=[
            AppointmentResponse(
                id=appointment.id,
                doctor=appointment.doctor,
                appointment_date=appointment.appointment_date,
                appointment_time=appointment.appointment_time,
                status=appointment.status,
            )
            for appointment in appointments
        ]
    )


@router.get(
    "/upcoming",
    response_model=AppointmentResponse | None,
)
async def get_upcoming_appointment(
    session: PatientSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    appointment = await get_upcoming_patient_appointment(
        patient_id=session.patient_id,
        db=db,
    )

    if appointment is None:
        return None

    return AppointmentResponse(
        id=appointment.id,
        doctor=appointment.doctor,
        appointment_date=appointment.appointment_date,
        appointment_time=appointment.appointment_time,
        status=appointment.status,
    )

@router.get(
    "/availability",
    response_model=AvailabilityResponse,
)
async def get_availability(
    doctor_id: UUID = Query(...),
    appointment_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await get_doctor_availability(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        db=db,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Doctor not found",
        )

    doctor, available_slots = result

    return AvailabilityResponse(
        doctor_id=doctor.id,
        doctor_name=doctor.name,
        date=appointment_date,
        available_slots=available_slots,
    )

@router.post(
    "",
    response_model=AppointmentResponse,
    status_code=201,
)
async def book_appointment(
    data: AppointmentCreate,
    session: PatientSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    try:
        appointment = await create_appointment(
            patient_id=session.patient_id,
            doctor_id=data.doctor_id,
            appointment_date=data.appointment_date,
            appointment_time=data.appointment_time,
            db=db,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    await db.refresh(
        appointment,
        attribute_names=["doctor"],
    )

    return AppointmentResponse(
        id=appointment.id,
        doctor=appointment.doctor,
        appointment_date=appointment.appointment_date,
        appointment_time=appointment.appointment_time,
        status=appointment.status,
    )