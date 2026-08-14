from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from schemas.session import SessionCreate, SessionResponse
from ai_core.service import create_patient_session
from ai_core.service import get_current_session
from app.models.patient_session import PatientSession
router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["Sessions"],
)

@router.post(
    "",
    response_model=SessionResponse,
)
async def create_session(
    data: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        session = await create_patient_session(
            phone=data.phone,
            db=db,
        )

    except ValueError:
        raise HTTPException(
            status_code=404,
            detail="Patient not found",
        )

    return SessionResponse(
        session_id=session.id,
        expires_at=session.expires_at,
        is_active=session.is_active,
    )

@router.get("/me")
async def get_current_session_info(
    session: PatientSession = Depends(get_current_session),
):
    return {
        "session_id": session.id,
        "patient_id": session.patient_id,
        "is_active": session.is_active,
    }