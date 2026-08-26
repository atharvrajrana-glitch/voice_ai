from datetime import date, datetime, time, timezone
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.doctor import Doctor
from app.core.hospital_schedule import (
    WORKING_DAYS,
    WORKING_SLOTS,
)

async def get_doctor_availability(
    doctor_id: UUID,
    appointment_date: date,
    db: AsyncSession,
) -> tuple[Doctor, list[time]] | None:

    # 1. Find doctor
    result = await db.execute(
        select(Doctor).where(
            Doctor.id == doctor_id
        )
    )

    doctor = result.scalar_one_or_none()

    if doctor is None:
        return None

    # 2. Hospital closed on weekends
    if appointment_date.weekday() not in WORKING_DAYS:
        return doctor, []

    # 2b. No slots for dates that have already fully passed
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    if appointment_date < today_ist:
        return doctor, []

    # 3. Get already booked slots
    result = await db.execute(
        select(Appointment.appointment_time)
        .where(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == appointment_date,
            Appointment.status == "scheduled",
        )
    )

    booked_slots = {
        row[0]
        for row in result.all()
    }

        # 4. Remove booked slots, and if booking for today, remove slots already in the past
        # 4. Remove booked slots, and if booking for today, remove slots already in the past (hospital local time)
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    is_today = appointment_date == now_ist.date()
    current_time_ist = now_ist.time()

    available_slots = [
        slot
        for slot in WORKING_SLOTS
        if slot not in booked_slots
        and not (is_today and slot <= current_time_ist)
    ]
    return doctor, available_slots
async def create_appointment(
    patient_id: UUID,
    doctor_id: UUID,
    appointment_date: date,
    appointment_time: time,
    db: AsyncSession,
) -> Appointment:

    # --------------------------------
    # 1. Validate doctor
    # --------------------------------

    result = await db.execute(
        select(Doctor).where(
            Doctor.id == doctor_id
        )
    )

    doctor = result.scalar_one_or_none()

    if doctor is None:
        raise ValueError("Doctor not found")

    # --------------------------------
    # 2. Validate date is not in past
    # --------------------------------

        # --------------------------------
    # 2. Validate date and time are not in the past
    # --------------------------------
        # --------------------------------
    # 2. Validate date and time are not in the past (hospital local time)
    # --------------------------------
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    if appointment_date < now_ist.date():
        raise ValueError(
            "Appointment date cannot be in the past"
        )
    if appointment_date == now_ist.date() and appointment_time <= now_ist.time():
        raise ValueError(
            "That time has already passed today. Please choose a later time."
        )

    # --------------------------------
    # 3. Validate hospital working day
    # --------------------------------

    if appointment_date.weekday() not in WORKING_DAYS:
        raise ValueError(
            "Hospital is closed on this day"
        )

    # --------------------------------
    # 4. Validate time slot
    # --------------------------------

    if appointment_time not in WORKING_SLOTS:
        raise ValueError(
            "Invalid appointment time slot"
        )

    # --------------------------------
    # 5. Check if slot is already booked
    # --------------------------------

    result = await db.execute(
        select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == appointment_date,
            Appointment.appointment_time == appointment_time,
            Appointment.status == "scheduled",
        )
    )

    existing_appointment = result.scalar_one_or_none()

    if existing_appointment is not None:
        raise ValueError(
            "This appointment slot is no longer available"
        )

    # --------------------------------
    # 6. Create appointment
    # --------------------------------

    appointment = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        status="scheduled",
    )

    db.add(appointment)

    await db.commit()
    await db.refresh(appointment)

    return appointment
