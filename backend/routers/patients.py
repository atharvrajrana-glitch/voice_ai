from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.patient import Patient
from app.models.patient_doctor import PatientDoctor
from app.models.doctor import Doctor
from schemas.patient import PatientResponse, DoctorSummary


router = APIRouter(
    prefix="/api/v1/patients",
    tags=["Patients"],
)


@router.get(
    "/by-phone/{phone}",
    response_model=PatientResponse,
)
async def get_patient_by_phone(
    phone: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Patient).where(Patient.phone == phone)
    )

    patient = result.scalar_one_or_none()

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found",
        )

    doctor_result = await db.execute(
        select(Doctor)
        .join(
            PatientDoctor,
            PatientDoctor.doctor_id == Doctor.id
        )
        .where(
            PatientDoctor.patient_id == patient.id
        )
    )

    doctors = doctor_result.scalars().all()

    return PatientResponse(
        id=patient.id,
        name=patient.name,
        phone=patient.phone,
        email=patient.email,
        doctors=[
            DoctorSummary.model_validate(doctor)
            for doctor in doctors
        ],
    )

