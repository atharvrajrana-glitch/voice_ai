from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lab_report import LabReport

async def get_latest_lab_report(patient_id: str, db: AsyncSession) -> LabReport | None:
    """Fetch the most recently created lab report for a patient , if any exists."""
    result = await db.execute(
        select(LabReport)
        .where(LabReport.patient_id == patient_id)
        .order_by(LabReport.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()