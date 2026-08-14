from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from schemas.doctor import (
    DoctorListResponse,
    DoctorResponse,
)
from ai_core.doctor_service import (
    get_all_doctors,
    get_doctors_by_department,
    get_doctors_by_specialization,
)


router = APIRouter(
    prefix="/api/v1/doctors",
    tags=["Doctors"],
)


@router.get(
    "",
    response_model=DoctorListResponse,
)
async def get_doctors(
    department: str | None = Query(default=None),
    specialization: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):

    if department:
        doctors = await get_doctors_by_department(
            department=department,
            db=db,
        )

    elif specialization:
        doctors = await get_doctors_by_specialization(
            specialization=specialization,
            db=db,
        )

    else:
        doctors = await get_all_doctors(db=db)

    return DoctorListResponse(
        doctors=[
            DoctorResponse.model_validate(doctor)
            for doctor in doctors
        ]
    )