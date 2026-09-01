"""Session-aware Groq orchestration for hospital information and live tools."""

import asyncio
import json
import logging
import os
from time import perf_counter
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from fastapi import Depends, Header, HTTPException
from dotenv import load_dotenv
from groq import Groq
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal, get_db  # noqa: import before relative path setup
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.patient_session import PatientSession
from ai_core.lab_report_service import get_latest_lab_report
from .system_prompt import SYSTEM_PROMPT
from .tool_registry import ToolContext, execute_tool, get_groq_tools

load_dotenv()

logger = logging.getLogger(__name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY"))
MODEL = "openai/gpt-oss-20b"
FALLBACK_REPLY = "Sorry, I wasn't able to work out an answer to that. Could you try asking again?"
MAX_TOOL_LOOPS = 10
MAX_HISTORY_CONTENTS = 4
SESSION_DURATION_HOURS = 1
SESSION_ACTIVITY_UPDATE_INTERVAL_SECONDS = 60
MODEL_REQUEST_TIMEOUT_SECONDS = 60
logger = logging.getLogger(__name__)
_conversation_history: dict[UUID, list[dict]] = {}
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
    messages.append({"role": "user", "content": patient_text})
    sources: list[str] = []

    available_tools = get_groq_tools()

    for loop_number in range(1, MAX_TOOL_LOOPS + 1):
        groq_started_timer = perf_counter()

        # Tools are available on all loops to handle tool-calling workflows
        current_tools = available_tools

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: client.chat.completions.create(
                        model=MODEL,
                        messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
                        tools=current_tools,
                        tool_choice="auto",
                        temperature=0,
                        max_tokens=200,
                    )
                ),
                timeout=MODEL_REQUEST_TIMEOUT_SECONDS,
            )
            # --- DEBUG INSPECTION LOG ---
            logger.info("ai_debug payload_inspection loop=%d total_messages=%d", loop_number, len(messages))
            for idx, msg in enumerate(messages):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")[:100]
                logger.info("ai_debug_msg [%d] role=%s content='%s'", idx, role, content)
            # -----------------------------
        except Exception:
            logger.exception("ai_core Groq request failed model=%s loop=%d", MODEL, loop_number)  
            return {"reply": FALLBACK_REPLY, "resolved": False, "language": "en", "sources": sources}
        
        finally:
            logger.info(
                "ai_timing groq_call_end request_id=%s loop=%d step_total_ms=%.1f",
                request_id,
                loop_number,
                (perf_counter() - groq_started_timer) * 1000,
            )

        if not response or not response.choices:
            return {"reply": FALLBACK_REPLY, "resolved": False, "language": "en", "sources": sources}

        choice = response.choices[0]
        message = choice.message

        # 1. Look for tool calls FIRST
        if message.tool_calls:
            # Append assistant message (even if empty) to track the tool call in conversation
            messages.append({"role": "assistant", "content": message.content or ""})
            
            for tool_call in message.tool_calls:
                name = tool_call.function.name
                # Parse arguments from JSON string
                try:
                    args = json.loads(tool_call.function.arguments)
                except:
                    args = {}
                
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
                
                # Append tool result as a user message with string content
                messages.append({
                    "role": "user",
                    "content": f"Tool '{name}' result: {json.dumps(result)}"
                })
            
            continue

        # 2. Extract text response
        raw = (message.content or "").strip()
        
        if not raw:
            # Check if we've had too many consecutive empty responses
            empty_count = sum(1 for msg in messages[-6:] if msg.get("role") == "assistant" and not msg.get("content", "").strip())
            
            # If we're at the last loop and still no response, return fallback
            if loop_number >= MAX_TOOL_LOOPS or empty_count >= 3:
                logger.warning("MAX_TOOL_LOOPS or too many empty responses: session_id=%s user_text='%s' loop=%d empty_count=%d", session_id, patient_text, loop_number, empty_count)
                return {"reply": FALLBACK_REPLY, "resolved": False, "language": "en", "sources": sources}
            # Otherwise continue looping to try again
            logger.info("EMPTY_RESPONSE_CONTINUING: loop=%d session_id=%s empty_count=%d", loop_number, session_id, empty_count)
            continue

        messages.append({"role": "assistant", "content": raw})
        if session_id:
            _conversation_history[session_id] = messages[-MAX_HISTORY_CONTENTS:]
            
        # 3. Return response
        final_response = {
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
    result = await db.execute(select(Appointment).options(selectinload(Appointment.doctor)).where(Appointment.patient_id == patient_id, Appointment.status == "scheduled").order_by(Appointment.appointment_date, Appointment.appointment_time))
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
    Yields text chunks as they are generated by Groq.
    Handles tool execution seamlessly between chunks.
    """
    if not patient_text or not patient_text.strip():
        yield "I didn't catch that. Could you say it again?"
        return

    context = ToolContext(db=db, session_id=session_id, patient_id=patient_id, user_text=patient_text)
    messages = list(_conversation_history.get(session_id, [])) if session_id else []
    messages.append({"role": "user", "content": patient_text})
    
    available_tools = get_groq_tools()
    full_response_text = ""
    executed_tool_calls: dict[str, Any] = {}
    for loop_number in range(1, MAX_TOOL_LOOPS + 1):
        # Tools are available on all loops to handle tool-calling workflows
        current_tools = available_tools
        
        try:
            logger.info("ai_debug stream_payload_inspection loop=%d total_messages=%d", loop_number, len(messages))
            for idx, msg in enumerate(messages):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")[:100] if isinstance(msg.get("content"), str) else ""
                logger.info("ai_debug_stream_msg [%d] role=%s content='%s'", idx, role, content)
            
            response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
                    tools=current_tools,
                    tool_choice="auto",
                    temperature=0.2,
                    max_tokens=250,
                    stream=True,
                )
            
            tool_calls = []
            assistant_message = {"role": "assistant", "content": ""}

            for chunk in response:
                try:
                    if chunk.choices[0].delta.content:
                        text_chunk = chunk.choices[0].delta.content
                        full_response_text += text_chunk
                        assistant_message["content"] += text_chunk
                        yield text_chunk
                        
                    if chunk.choices[0].delta.tool_calls:
                        tool_calls.extend(chunk.choices[0].delta.tool_calls)
                except (AttributeError, KeyError):
                    # Handle malformed chunks gracefully
                    continue
                except Exception as chunk_err:
                    logger.warning("Chunk processing error (continuing): %s", chunk_err)
                    continue

        except Exception as e:
            logger.exception("ai_core Groq streaming failed")
            yield "Sorry, could you say that again? I didn't quite understand."
            return

        # If tools were called, execute them and run the next loop
        if tool_calls:
            messages.append(assistant_message)
            
            # Build tool results as strings instead of dicts
            for tool_call in tool_calls:
                name = tool_call.function.name
                try:
                    args_str = tool_call.function.arguments
                    logger.info("TOOL_CALL_RAW: name=%s args_raw=%s", name, args_str[:100] if args_str else "")
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError as json_err:
                    logger.warning("TOOL_ARGS_JSON_ERROR: name=%s error=%s raw=%s", name, str(json_err), args_str[:100] if args_str else "")
                    # For emergency alert, try to salvage it
                    if name == "trigger_emergency_alert":
                        args = {"symptom_description": "Emergency alert triggered - patient in distress"}
                    else:
                        args = {}
                except Exception as parse_err:
                    logger.warning("TOOL_ARGS_PARSE_ERROR: name=%s error=%s", name, str(parse_err))
                    args = {}
                
                call_signature = f"{name}:{args_str}"

                

                if call_signature in executed_tool_calls:
                    logger.warning("DUPLICATE_TOOL_CALL_SKIPPED: name=%s args=%s", name, args_str[:100] if args_str else "")
                    # Don't re-inject the same result — the model already saw and
                    # responded to it once. Tell it explicitly to stop repeating instead.
                    messages.append({
                        "role": "user",
                        "content": f"Tool '{name}' result: You already have this information. Do not call this tool again or repeat your previous answer — just wait for the patient's next response."
                    })
                    continue

                try:
                    result = await execute_tool(name, args, context)
                except Exception as e:
                    logger.error("TOOL_EXEC_ERROR: name=%s error=%s", name, str(e))
                    result = f"Error executing {name}: {str(e)}"
                executed_tool_calls[call_signature] = result

                # Append as a user message with the tool result as a string
                messages.append({
                    "role": "user",
                    "content": f"Tool '{name}' result: {json.dumps(result)}"
                })
            
            continue # Go to loop 2 to generate the final voice response based on tool data
        if not assistant_message["content"].strip():
            logger.warning("EMPTY_MODEL_RESPONSE: session_id=%s user_text='%s'", session_id, patient_text)
            yield "Sorry, could you say that again?"
            return
        # If no tools were called, generation is complete.
        messages.append(assistant_message)
        if session_id:
            _conversation_history[session_id] = messages[-MAX_HISTORY_CONTENTS:]
        break
