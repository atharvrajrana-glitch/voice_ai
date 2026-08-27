from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import re
from app.models.doctor import Doctor


async def get_all_doctors(
    db: AsyncSession,
) -> list[Doctor]:

    result = await db.execute(
        select(Doctor)
        .order_by(Doctor.name.asc())
    )

    return list(result.scalars().all())


async def get_doctors_by_department(
    department: str,
    db: AsyncSession,
) -> list[Doctor]:

    result = await db.execute(
        select(Doctor)
        .where(
            Doctor.department.ilike(department)
        )
        .order_by(Doctor.name.asc())
    )

    return list(result.scalars().all())




async def get_doctors_by_specialization(
    specialization: str,
    db: AsyncSession,
) -> list[Doctor]:

    cleaned = specialization.strip()
    # Normalize person-noun forms to field-noun forms: "cardiologist" -> "cardiolog",
    # "dermatologist" -> "dermatolog", so it substring-matches "Cardiology"/"Dermatology"
    cleaned = re.sub(r'(ist)$', '', cleaned, flags=re.IGNORECASE)
    # Handle British spelling variants: "orthopaedic" -> "orthop"
    cleaned = re.sub(r'(ae|a)?dic$', '', cleaned, flags=re.IGNORECASE)

    result = await db.execute(
        select(Doctor)
        .where(
            Doctor.specialization.ilike(f"%{cleaned}%")
        )
        .order_by(Doctor.name.asc())
    )
    doctors = list(result.scalars().all())

    if not doctors and cleaned != specialization:
        # Fall back to the original raw term in case normalization over-stripped
        result = await db.execute(
            select(Doctor)
            .where(
                Doctor.specialization.ilike(f"%{specialization}%")
            )
            .order_by(Doctor.name.asc())
        )
        doctors = list(result.scalars().all())

    return doctors




async def get_doctors_by_name(
    name: str,
    db: AsyncSession,
) -> list[Doctor]:
    """Search doctors by name (partial match, ignoring titles/punctuation)."""
    cleaned = re.sub(r'[.]', '', name)
    cleaned = re.sub(r'^(dr|doctor)\s+', '', cleaned, flags=re.IGNORECASE).strip()

    result = await db.execute(
        select(Doctor)
        .where(
            Doctor.name.ilike(f"%{cleaned}%")
        )
        .order_by(Doctor.name.asc())
    )

    return list(result.scalars().all())