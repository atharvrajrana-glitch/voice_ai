"""
The AI core service — running on Gemini 3.5 Flash, now optionally
grounded in retrieved hospital policy context (RAG).

Input:  plain text (what the patient said, transcribed by Module 1)
Output: {"reply": str, "resolved": bool, "language": str, "sources": list}

Retrieval failures never crash this — if the vector store has nothing
relevant (or errors), the AI core just answers using its own knowledge
and the same rules as before, exactly like it did before RAG existed.
"""

import json
import os
from google import genai
from google.genai import types
from .system_prompt import SYSTEM_PROMPT
from RAG.retrieval import retrieve_hospital_context
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.patient import Patient
from app.models.patient_session import PatientSession
from app.models.appointment import Appointment
from fastapi import Depends, Header, HTTPException
from app.core.database import get_db
from app.core.hospital_schedule import (
    WORKING_DAYS,
    WORKING_SLOTS,
)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

MODEL = "gemini-3.5-flash"
SESSION_DURATION_HOURS = 1

FALLBACK_REPLY = "Sorry, I wasn't able to work out an answer to that. Could you try asking again?"


def get_ai_response(patient_text: str) -> dict:
    if not patient_text or not patient_text.strip():
        return {"reply": "I didn't catch that. Could you say it again?", "resolved": False, "language": "unknown", "sources": []}

    context, sources = retrieve_hospital_context(patient_text)

    if context:
        user_content = (
            f"Hospital-specific reference information (use this if it's "
            f"relevant to the question; ignore it if it's not):\n"
            f"----------------\n{context}\n----------------\n\n"
            f"Patient question:\n{patient_text}"
        )
    else:
        user_content = patient_text

    response = client.models.generate_content(
        model=MODEL,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )

    raw = (response.text or "").strip()
    print(f"[ai_core] raw Gemini response: {raw!r}")

    try:
        data = json.loads(raw)
        if "reply" not in data or not str(data["reply"]).strip():
            raise ValueError("empty or missing reply field")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[ai_core] parse/validation failed: {e}")
        data = {"reply": FALLBACK_REPLY, "resolved": False, "language": "unknown"}

    data["sources"] = sources
    return data 

async def create_patient_session(
    phone: str,
    db: AsyncSession,
) -> PatientSession:

    # Find patient using phone number
    result = await db.execute(
        select(Patient).where(Patient.phone == phone)
    )

    patient = result.scalar_one_or_none()

    if patient is None:
        raise ValueError("Patient not found")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=SESSION_DURATION_HOURS)

    session = PatientSession(
        patient_id=patient.id,
        created_at=now,
        last_activity_at=now,
        expires_at=expires_at,
        is_active=True,
    )

    db.add(session)

    await db.commit()
    await db.refresh(session)

    return session

async def get_current_session(
    x_session_id: UUID = Header(..., alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db),
) -> PatientSession:

    result = await db.execute(
        select(PatientSession).where(
            PatientSession.id == x_session_id,
            PatientSession.is_active.is_(True),
        )
    )

    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or inactive session",
        )

    now = datetime.now(timezone.utc)

    if session.expires_at <= now:
        session.is_active = False
        await db.commit()

        raise HTTPException(
            status_code=401,
            detail="Session expired",
        )

    # Refresh session activity/expiry
    session.last_activity_at = now

    await db.commit()

    return session

async def get_patient_appointments(
    patient_id: UUID,
    db: AsyncSession,
) -> list[Appointment]:

    result = await db.execute(
        select(Appointment)
        .options(selectinload(Appointment.doctor))
        .where(
            Appointment.patient_id == patient_id
        )
        .order_by(
            Appointment.appointment_date.asc(),
            Appointment.appointment_time.asc(),
        )
    )

    return list(result.scalars().all())

async def get_upcoming_patient_appointment(
    patient_id: UUID,
    db: AsyncSession,
) -> Appointment | None:

    now = datetime.now(timezone.utc)

    today = now.date()
    # PostgreSQL stores appointment_time as TIME WITHOUT TIME ZONE.
    current_time = now.time().replace(tzinfo=None)

    result = await db.execute(
        select(Appointment)
        .options(selectinload(Appointment.doctor))
        .where(
            Appointment.patient_id == patient_id,
            Appointment.status == "scheduled",
            (
                (Appointment.appointment_date > today)
                |
                (
                    (Appointment.appointment_date == today)
                    &
                    (Appointment.appointment_time >= current_time)
                )
            ),
        )
        .order_by(
            Appointment.appointment_date.asc(),
            Appointment.appointment_time.asc(),
        )
        .limit(1)
    )

    return result.scalar_one_or_none()
