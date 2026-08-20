"""Session-aware Gemini orchestration for hospital information and live tools."""

import asyncio
import json
import logging
import os
from time import perf_counter
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from fastapi import Depends, Header, HTTPException
from google import genai
from google.genai import types
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal, get_db
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.patient_session import PatientSession
from .system_prompt import SYSTEM_PROMPT
from .tool_registry import ToolContext, execute_tool, get_gemini_tools



logger = logging.getLogger(__name__)
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
MODEL = "gemini-3.5-flash"
FALLBACK_REPLY = "Sorry, I wasn't able to work out an answer to that. Could you try asking again?"
MAX_TOOL_LOOPS = 10
MAX_HISTORY_CONTENTS = 20
SESSION_DURATION_HOURS = 1
SESSION_ACTIVITY_UPDATE_INTERVAL_SECONDS = 60
MODEL_REQUEST_TIMEOUT_SECONDS = 60
logger = logging.getLogger(__name__)
_conversation_history: dict[UUID, list[types.Content]] = {}
SHORT_CONFIRMATION_WORDS = {"yes", "no", "yep", "nope", "sure", "ok", "cancel", "yeah"}

class VoiceResponseSchema(BaseModel):
    reply: str = Field(description="Short conversational response for TTS, max 2 sentences.")
    resolved: bool = Field(description="Whether the user request was fully addressed.")
    language: str = Field(default="en", description="Language code used in the reply.")

async def get_ai_response(patient_text: str, session_id: UUID | None, patient_id: UUID | None, db: AsyncSession) -> dict:
    request_id = uuid4().hex[:8]
    request_started_timer = perf_counter()
    logger.info("ai_timing request_start request_id=%s", request_id)
    try:
        return await _get_ai_response(patient_text, session_id, patient_id, db, request_id)
    finally:
        logger.info(
            "ai_timing request_end request_id=%s request_total_ms=%.1f",
            request_id,
            (perf_counter() - request_started_timer) * 1000,
        )



async def _get_ai_response(
    patient_text: str,
    session_id: UUID | None,
    patient_id: UUID | None,
    db: AsyncSession,
    request_id: str,
) -> dict:
    if not patient_text or not patient_text.strip():
        return {"reply": "I didn't catch that. Could you say it again?", "resolved": False, "language": "unknown", "sources": []}

    clean_text = patient_text.strip().lower()
    is_short_word = clean_text in SHORT_CONFIRMATION_WORDS
    
    if not is_short_word and not session_id:
        cached = await get_cached_response(clean_text) 
        if cached:
            logger.info("ai_cache_hit text='%s'", clean_text)
            return cached
    else:
        logger.info("ai_cache_bypass text='%s' reason='active_session_or_short_word'", clean_text)

    logger.info("ai_cache_miss text='%s'", clean_text)
    context = ToolContext(db=db, session_id=session_id, patient_id=patient_id, user_text=patient_text)
    messages = list(_conversation_history.get(session_id, [])) if session_id else []
    messages.append(types.Content(role="user", parts=[types.Part.from_text(text=patient_text)]))
    sources: list[str] = []

    available_tools = get_gemini_tools()

    for loop_number in range(1, MAX_TOOL_LOOPS + 1):
        gemini_started_timer = perf_counter()

        # Tools active on loop 1, deactivated on loop 2 for final voice synthesis
        current_tools = available_tools if loop_number == 1 else None

        # ULTRA-FAST CONFIG: Removed response_schema and thinking_config
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=current_tools,
            temperature=0,          # Low temp for fast, deterministic routing
            max_output_tokens=200,    # Cap output for short voice replies
        )

        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=MODEL,
                    contents=messages,
                    config=config,
                ),
                timeout=MODEL_REQUEST_TIMEOUT_SECONDS, # Make sure this is 15, not 60!
            )
            # --- DEBUG INSPECTION LOG ---
            logger.info("ai_debug payload_inspection loop=%d total_messages=%d", loop_number, len(messages))
            for idx, msg in enumerate(messages):
                role = getattr(msg, "role", "unknown")
                text_parts = [p.text for p in (msg.parts or []) if hasattr(p, "text") and p.text]
                tool_parts = [p.function_call.name for p in (msg.parts or []) if hasattr(p, "function_call") and p.function_call]
                logger.info("ai_debug_msg [%d] role=%s text='%s' tools=%s", idx, role, " ".join(text_parts)[:100], tool_parts)
            # -----------------------------
        except Exception:
            logger.exception("ai_core Gemini request failed model=%s loop=%d", MODEL, loop_number)  
            return {"reply": FALLBACK_REPLY, "resolved": False, "language": "en", "sources": sources}
        
        finally:
            logger.info(
                "ai_timing gemini_call_end request_id=%s loop=%d step_total_ms=%.1f",
                request_id,
                loop_number,
                (perf_counter() - gemini_started_timer) * 1000,
            )

        candidate = response.candidates[0] if response and response.candidates else None
        content = candidate.content if candidate and candidate.content else None
        if content is None:
            return {"reply": FALLBACK_REPLY, "resolved": False, "language": "en", "sources": sources}

        # 1. Look for function calls FIRST to avoid the SDK warning
        calls = [part for part in (content.parts or []) if part.function_call]
        if calls:
            messages.append(content)
            responses: list[types.Part] = []
            for part in calls:
                name = part.function_call.name
                args = dict(part.function_call.args or {})
                tool_started_timer = perf_counter()
                try:
                    result = await execute_tool(name, args, context)
                finally:
                    logger.info(
                        "ai_timing tool_execution_end request_id=%s loop=%d tool=%s step_total_ms=%.1f",
                        request_id,
                        loop_number,
                        name,
                        (perf_counter() - tool_started_timer) * 1000,
                    )
                for source in result.get("sources", []):
                    if source not in sources:
                        sources.append(source)
                responses.append(types.Part.from_function_response(name=name, response={"result": result}))
            messages.append(types.Content(role="tool", parts=responses))
            continue

        # 2. Extract text SAFELY (ignores function_call parts)
        raw = "".join([part.text for part in (content.parts or []) if not part.function_call]).strip()
        
        if not raw:
            return {"reply": FALLBACK_REPLY, "resolved": False, "language": "en", "sources": sources}

        messages.append(content)
        if session_id:
            _conversation_history[session_id] = messages[-MAX_HISTORY_CONTENTS:]
            
        # 3. Bypass JSON parsing completely and wrap the plain text directly
        final_response ={
            "reply": raw,
            "resolved": True,
            "language": "en", 
            "sources": sources
        }
        if not is_short_word and not session_id:
            await set_cached_response(clean_text, final_response)
            
        return final_response

def _parse_response(raw: str, sources: list[str]) -> dict:
    try:
        data = json.loads(raw)
        return {
            "reply": str(data.get("reply", FALLBACK_REPLY)),
            "resolved": bool(data.get("resolved", False)),
            "language": str(data.get("language", "unknown")),
            "sources": sources,
        }
    except Exception:
        logger.warning("ai_core response JSON fallback triggered: %s", raw)
        return {"reply": raw if raw else FALLBACK_REPLY, "resolved": False, "language": "unknown", "sources": sources}

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


async def _record_session_activity(session_id: UUID, activity_at: datetime) -> None:
    """Persist a throttled activity timestamp without holding up the request."""
    try:
        async with AsyncSessionLocal() as activity_db:
            await activity_db.execute(
                update(PatientSession)
                .where(
                    PatientSession.id == session_id,
                    PatientSession.is_active.is_(True),
                    PatientSession.expires_at > activity_at,
                )
                .values(last_activity_at=activity_at)
            )
            await activity_db.commit()
    except Exception:
        # Activity tracking is best-effort only. It must never affect authorization
        # or the voice response after the request has already been authorized.
        logger.exception("Failed to update activity for session_id=%s", session_id)


async def _validate_and_refresh_session(session_id: UUID, db: AsyncSession) -> PatientSession | None:
    session = (await db.execute(select(PatientSession).where(PatientSession.id == session_id, PatientSession.is_active.is_(True)))).scalar_one_or_none()
    if session is None:
        return None
    now = datetime.now(timezone.utc)
    if session.expires_at <= now:
        session.is_active = False
        await db.commit()
        return None
    if now - session.last_activity_at >= timedelta(seconds=SESSION_ACTIVITY_UPDATE_INTERVAL_SECONDS):
        # Use an independent session because the request-scoped one will be closed
        # when the response ends. This write is observational, never authorization.
        asyncio.create_task(_record_session_activity(session.id, now))
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



async def stream_ai_response(patient_text: str, session_id: UUID | None, patient_id: UUID | None, db):
    """
    Yields text chunks as they are generated by Gemini.
    Handles tool execution seamlessly between chunks.
    """
    if not patient_text or not patient_text.strip():
        yield "I didn't catch that. Could you say it again?"
        return

    context = ToolContext(db=db, session_id=session_id, patient_id=patient_id, user_text=patient_text)
    messages = list(_conversation_history.get(session_id, [])) if session_id else []
    messages.append(types.Content(role="user", parts=[types.Part.from_text(text=patient_text)]))
    
    available_tools = get_gemini_tools()
    full_response_text = ""

    for loop_number in range(1, MAX_TOOL_LOOPS + 1):
        # Tools are only available on the first loop
        current_tools = available_tools if loop_number == 1 else None
        
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=current_tools,
            temperature=0.2,
            max_output_tokens=250,
        )

        try:
            # Use generate_content_stream instead of 
            logger.info("ai_debug stream_payload_inspection loop=%d total_messages=%d", loop_number, len(messages))
            for idx, msg in enumerate(messages):
                role = getattr(msg, "role", "unknown")
                text_parts = [p.text for p in (msg.parts or []) if hasattr(p, "text") and p.text]
                tool_parts = [p.function_call.name for p in (msg.parts or []) if hasattr(p, "function_call") and p.function_call]
                logger.info("ai_debug_stream_msg [%d] role=%s text='%s' tools=%s", idx, role, " ".join(text_parts)[:100], tool_parts)
            # -------------------------------------------
            response_stream = await client.aio.models.generate_content_stream(
                model=MODEL,
                contents=messages,
                config=config,
            )
            
            tool_calls = []
            generated_content = types.Content(role="model", parts=[])

            async for chunk in response_stream:
                if not chunk.candidates or not chunk.candidates[0].content.parts:
                    continue
                    
                for part in chunk.candidates[0].content.parts:
                    if part.function_call:
                        tool_calls.append(part.function_call)
                        generated_content.parts.append(part)
                    elif part.text:
                        text_chunk = part.text
                        full_response_text += text_chunk
                        generated_content.parts.append(part)
                        # Yield the chunk directly to the FastAPI stream!
                        yield text_chunk

        except Exception as e:
            logger.exception("ai_core Gemini streaming failed")
            yield "Sorry, I am having trouble connecting to the hospital network right now."
            return

        # If tools were called, execute them and run the next loop
        if tool_calls:
            messages.append(generated_content)
            responses = []
            
            for call in tool_calls:
                name = call.name
                args = dict(call.args or {})
                try:
                    result = await execute_tool(name, args, context)
                except Exception as e:
                    result = f"Error executing {name}: {str(e)}"
                
                responses.append(types.Part.from_function_response(name=name, response={"result": result}))
            
            messages.append(types.Content(role="tool", parts=responses))
            continue # Go to loop 2 to generate the final voice response based on tool data
            
        # If no tools were called, generation is complete.
        messages.append(generated_content)
        if session_id:
            _conversation_history[session_id] = messages[-MAX_HISTORY_CONTENTS:]
        break
