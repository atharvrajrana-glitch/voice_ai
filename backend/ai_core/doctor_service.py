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

    result = await db.execute(
        select(Doctor)
        .where(
            Doctor.specialization.ilike(f"%{specialization}%")
        )
        .order_by(Doctor.name.asc())
    )

    return list(result.scalars().all())




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