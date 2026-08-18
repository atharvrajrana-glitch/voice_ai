from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from schemas.session import PatientSignUp, SessionCreate, SessionResponse
from ai_core.service import close_patient_session, create_patient_session, register_patient_and_create_session
from ai_core.service import get_current_session
from app.models.patient_session import PatientSession
from app.models.patient import Patient


router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["Sessions"],
)


@router.post("/signup", response_model=SessionResponse, status_code=201)
async def sign_up_patient(data: PatientSignUp, db: AsyncSession = Depends(get_db)):
    try:
        session = await register_patient_and_create_session(
            name=data.name,
            phone=data.phone,
            email=data.email,
            db=db,
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A patient with this phone number or email already exists.")

    return SessionResponse(
        session_id=session.id,
        expires_at=session.expires_at,
        is_active=session.is_active,
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
    db: AsyncSession = Depends(get_db),
):
    patient = await db.get(Patient, session.patient_id)
    return {
        "session_id": session.id,
        "patient_id": session.patient_id,
        "name": patient.name if patient else "",
        "is_active": session.is_active,
    }


@router.post("/logout", status_code=204)
async def logout(
    session: PatientSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    await close_patient_session(session, db)
