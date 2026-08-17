"""Session-aware Gemini orchestration for hospital information and live tools."""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.patient_session import PatientSession
from .system_prompt import SYSTEM_PROMPT
from .tool_registry import ToolContext, execute_tool, get_gemini_tools

logger = logging.getLogger(__name__)
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
FALLBACK_REPLY = "Sorry, I wasn't able to work out an answer to that. Could you try asking again?"
MAX_TOOL_LOOPS = 10
MAX_HISTORY_CONTENTS = 20
SESSION_DURATION_HOURS = 1
MODEL_REQUEST_TIMEOUT_SECONDS = 60

_conversation_history: dict[UUID, list[types.Content]] = {}


async def get_ai_response(patient_text: str, session_id: UUID | None, patient_id: UUID | None, db: AsyncSession) -> dict:
    if not patient_text or not patient_text.strip():
        return {"reply": "I didn't catch that. Could you say it again?", "resolved": False, "language": "unknown", "sources": []}

    context = ToolContext(db=db, session_id=session_id, patient_id=patient_id, user_text=patient_text)
    messages = list(_conversation_history.get(session_id, [])) if session_id else []
    messages.append(types.Content(role="user", parts=[types.Part.from_text(text=patient_text)]))
    sources: list[str] = []
    config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, tools=get_gemini_tools())

    for _ in range(MAX_TOOL_LOOPS):
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=MODEL,
                    contents=messages,
                    config=config,
                ),
                timeout=MODEL_REQUEST_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.error("ai_core Gemini request timed out model=%s", MODEL)
            return {"reply": FALLBACK_REPLY, "resolved": False, "language": "unknown", "sources": sources}
        except Exception:
            logger.exception("ai_core Gemini request failed model=%s", MODEL)
            return {"reply": FALLBACK_REPLY, "resolved": False, "language": "unknown", "sources": sources}

        candidate = response.candidates[0] if response and response.candidates else None
        content = candidate.content if candidate and candidate.content else None
        if content is None:
            return {"reply": FALLBACK_REPLY, "resolved": False, "language": "unknown", "sources": sources}

        calls = [part for part in (content.parts or []) if part.function_call]
        if calls:
            messages.append(content)
            responses: list[types.Part] = []
            for part in calls:
                name = part.function_call.name
                args = dict(part.function_call.args or {})
                result = await execute_tool(name, args, context)
                for source in result.get("sources", []):
                    if source not in sources:
                        sources.append(source)
                responses.append(types.Part.from_function_response(name=name, response={"result": result}))
            messages.append(types.Content(role="tool", parts=responses))
            continue

        raw = next((part.text for part in (content.parts or []) if part.text), "").strip()
        if not raw:
            return {"reply": FALLBACK_REPLY, "resolved": False, "language": "unknown", "sources": sources}
        messages.append(content)
        if session_id:
            _conversation_history[session_id] = messages[-MAX_HISTORY_CONTENTS:]
        return _parse_response(raw, sources)

    logger.warning("ai_core tool loop limit reached")
    return {"reply": FALLBACK_REPLY, "resolved": False, "language": "unknown", "sources": sources}


def _parse_response(raw: str, sources: list[str]) -> dict:
    try:
        data = json.loads(raw)
        if not str(data.get("reply", "")).strip():
            raise ValueError("missing reply")
    except (json.JSONDecodeError, ValueError):
        logger.info("ai_core response parse_failed")
        data = {"reply": FALLBACK_REPLY, "resolved": False, "language": "unknown"}
    return {"reply": str(data["reply"]), "resolved": bool(data.get("resolved", False)), "language": str(data.get("language", "unknown")), "sources": sources}


async def create_patient_session(phone: str, db: AsyncSession) -> PatientSession:
    patient = (await db.execute(select(Patient).where(Patient.phone == phone))).scalar_one_or_none()
    if patient is None:
        raise ValueError("Patient not found")
    now = datetime.now(timezone.utc)
    session = PatientSession(patient_id=patient.id, created_at=now, last_activity_at=now, expires_at=now + timedelta(hours=SESSION_DURATION_HOURS), is_active=True)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def register_patient_and_create_session(name: str, phone: str, email: str | None, db: AsyncSession) -> PatientSession:
    """Create a patient and their first authenticated session in one transaction."""
    patient = Patient(name=name.strip(), phone=phone.strip(), email=email.strip() if email and email.strip() else None)
    db.add(patient)
    await db.flush()

    now = datetime.now(timezone.utc)
    session = PatientSession(
        patient_id=patient.id,
        created_at=now,
        last_activity_at=now,
        expires_at=now + timedelta(hours=SESSION_DURATION_HOURS),
        is_active=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def _validate_and_refresh_session(session_id: UUID, db: AsyncSession) -> PatientSession | None:
    session = (await db.execute(select(PatientSession).where(PatientSession.id == session_id, PatientSession.is_active.is_(True)))).scalar_one_or_none()
    if session is None:
        return None
    now = datetime.now(timezone.utc)
    if session.expires_at <= now:
        session.is_active = False
        await db.commit()
        return None
    session.last_activity_at = now
    await db.commit()
    return session


async def close_patient_session(session: PatientSession, db: AsyncSession) -> None:
    """Invalidate the active session immediately when the patient signs out."""
    session.is_active = False
    await db.commit()
    _conversation_history.pop(session.id, None)


async def get_current_session(x_session_id: UUID = Header(..., alias="X-Session-ID"), db: AsyncSession = Depends(get_db)) -> PatientSession:
    session = await _validate_and_refresh_session(x_session_id, db)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid, inactive, or expired session")
    return session


async def get_patient_appointments(patient_id: UUID, db: AsyncSession) -> list[Appointment]:
    result = await db.execute(select(Appointment).options(selectinload(Appointment.doctor)).where(Appointment.patient_id == patient_id).order_by(Appointment.appointment_date, Appointment.appointment_time))
    return list(result.scalars().all())


async def get_upcoming_patient_appointment(patient_id: UUID, db: AsyncSession) -> Appointment | None:
    now = datetime.now(timezone.utc)
    current_time = now.time().replace(tzinfo=None)
    result = await db.execute(
        select(Appointment).options(selectinload(Appointment.doctor)).where(
            Appointment.patient_id == patient_id,
            Appointment.status == "scheduled",
            (Appointment.appointment_date > now.date()) | ((Appointment.appointment_date == now.date()) & (Appointment.appointment_time >= current_time)),
        ).order_by(Appointment.appointment_date, Appointment.appointment_time).limit(1)
    )
    return result.scalar_one_or_none()
