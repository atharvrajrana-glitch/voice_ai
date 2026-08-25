"""Groq tool declarations and trusted in-process tool dispatch."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, time, datetime, timezone
from typing import Any
from uuid import UUID
import asyncio  
from sqlalchemy.ext.asyncio import AsyncSession

from RAG.retrieval import retrieve_hospital_context
from ai_core.availability_service import create_appointment, get_doctor_availability
from ai_core.doctor_service import get_all_doctors, get_doctors_by_department, get_doctors_by_specialization, get_doctors_by_name 
from patient_docs.service import answer_from_document
from ai_core.notification import send_twilio_sms
from app.models.patient import Patient
from sqlalchemy import select
        
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolContext:
    """Trusted data derived from the HTTP request, never Groq arguments."""

    db: AsyncSession
    session_id: UUID | None
    patient_id: UUID | None
    user_text: str


@dataclass(frozen=True)
class PendingBooking:
    doctor_id: UUID
    appointment_date: date
    appointment_time: time


_pending_bookings: dict[UUID, PendingBooking] = {}


def _groq_tool(name: str, description: str, properties: dict, required: list[str] = None) -> dict:
    """Create a Groq tool definition."""
    schema_props = {}
    for k, v in properties.items():
        base_type = v.get("type", "string")
        # Allow a field to accept null (e.g. optional params the model omits by passing null)
        prop_def = {"type": [base_type, "null"] if v.get("nullable") else base_type}
        if "description" in v:
            prop_def["description"] = v["description"]
        if "enum" in v:
            prop_def["enum"] = v["enum"]
        if "format" in v:
            prop_def["format"] = v["format"]
        schema_props[k] = prop_def
    
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": schema_props,
                "required": required or []
            }
        }
    }

def get_groq_tools() -> list[dict]:
    """Returns the consolidated, highly-optimized list of tools for Groq."""
    today = datetime.now(timezone.utc).date()
    tools = [
        _groq_tool(
            "search_hospital", 
            "Search hospital policies, facilities, billing, insurance, pharmacy, departments, or visiting hours. Do not use for patient-specific data.", 
            {"question": {"type": "string"}}, 
            ["question"]
        ),
        # 1. CONSOLIDATED: Appointments Lookup
        _groq_tool(
            "get_patient_appointments",
            "Get authenticated patient appointments. Use filter='upcoming' for next scheduled appointment, or filter='all' for complete history. Never accept a patient ID.",
            {
                "filter": {
                    "type": "string",
                    "enum": ["upcoming", "all"],
                    "description": "Fetch only the next upcoming appointment or all appointments."
                }
            },
            ["filter"]
        ),
        _groq_tool(
            "find_doctors", 
            "Find doctors by department, specialization, or doctor name. Provide one of: department, specialization, or query.", 
            {
                "department": {"type": "string", "description": "Department name (e.g., Cardiology)"},
                "specialization": {"type": "string", "description": "Doctor specialty (e.g., cardiologist)"},
                "query": {"type": "string", "description": "Doctor's full name or partial name (e.g., Rajesh Sharma)"}
            }
        ),
        # 2. CONSOLIDATED: Appointment Booking Workflow
        _groq_tool(
            "manage_appointment",
            "Manage booking process. Use action='check' to check slots on a date, or action='book' to finalize an appointment after user confirms the exact time.",
            {
                "action": {"type": "string", "enum": ["check", "book"]},
                "doctor_id": {"type": "string", "description": "Doctor UUID"},
                "appointment_date": {"type": "string", "format": "date", "description": f"Date in YYYY-MM-DD format (today is {today.isoformat()}; use future dates only)"},
                "appointment_time": {"type": "string", "nullable": True, "description": "HH:MM (required only if action is 'book'); pass null when action is 'check'"}
            },
            ["action", "doctor_id", "appointment_date"]
        ),
        _groq_tool(
            "patient_document_qa", 
            "Answer a question about the authenticated patient's uploaded document. Never accept a patient ID or document content.", 
            {"question": {"type": "string"}}, 
            ["question"]
        ),
        _groq_tool(
            "trigger_emergency_alert",
            "REQUIRED for emergencies: call this tool before replying whenever the signed-in patient reports chest pain, heart attack, stroke, severe bleeding, severe breathing difficulty, unconsciousness, or any emergency. Do not ask a question first and do not provide a medical assessment before calling it.",
            {"symptom_description": {"type": "string", "description": "A brief summary of what the patient said."}},
            ["symptom_description"]
        ),
    ]
    return tools

def _needs_session(context: ToolContext) -> dict[str, Any] | None:
    if context.session_id is None or context.patient_id is None:
        return {"ok": False, "error": "Please sign in before accessing your appointment or document information."}
    return None


def _doctor_data(doctor: Any) -> dict[str, str]:
    return {"id": str(doctor.id), "name": doctor.name, "specialization": doctor.specialization, "department": doctor.department}


def _is_confirmation(text: str) -> bool:
    normalized = " ".join(text.lower().strip().split()).strip(".!?,")
    exact_matches = {"yes", "yes please", "confirm", "confirm it", "book it", "yes book it", "go ahead", "please proceed", "yeah", "yep", "sure", "ok", "okay"}
    if normalized in exact_matches:
        return True
    # Handle speech-recognition noise/extra words: "yes alphabet", "yeah sure book it", etc.
    starting_words = ("yes", "yeah", "yep", "sure", "confirm", "book it", "go ahead", "okay", "ok")
    return normalized.startswith(starting_words)

async def execute_tool(name: str, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Run only allow-listed tools and return minimal JSON-safe values."""
    try:
        logger.info("TOOL_SELECTED: %s", name)
        if name == "search_hospital":
            hospital_context, sources = await retrieve_hospital_context(str(args["question"]).strip())
            result = {"ok": bool(hospital_context), "context": hospital_context or "", "sources": sources}
        elif name == "find_doctors":
            department = str(args.get("department") or "").strip()
            specialization = str(args.get("specialization") or "").strip()
            query = str(args.get("query") or "").strip()

            if department:
                doctors = await get_doctors_by_department(department, context.db)
            elif query:
                # If query is provided, search by name first (prioritize exact doctor name)
                doctors = await get_doctors_by_name(query, context.db)
                # If no match by name, try specialization from query
                if not doctors and specialization:
                    doctors = await get_doctors_by_specialization(specialization, context.db)
            elif specialization:
                # Only if no query provided, search by specialization
                doctors = await get_doctors_by_specialization(specialization, context.db)
            else:
                doctors = await get_all_doctors(context.db)

            result = {"ok": True, "doctors": [_doctor_data(doctor) for doctor in doctors]}
        else:
            session_error = _needs_session(context)
            if session_error:
                return session_error
            result = await _execute_patient_tool(name, args, context)
        logger.info("TOOL_EXECUTED: %s; TOOL_RESULT: %s", name, "success" if result.get("ok") else "failed")
        return result
    except (KeyError, TypeError, ValueError):
        logger.info("TOOL_EXECUTED: %s; TOOL_RESULT: invalid_input", name)
        return {"ok": False, "error": "I could not understand the appointment details. Please provide the doctor, date, and time again."}
    except Exception:
        logger.exception("TOOL_EXECUTED: %s; TOOL_RESULT: failed", name)
        return {"ok": False, "error": "The hospital system could not complete that request right now."}


async def _execute_patient_tool(name: str, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from ai_core.service import get_patient_appointments, get_upcoming_patient_appointment

    # -------------------------------------------------------------
    # 1. APPOINTMENTS LOOKUP (Consolidated + Legacy)
    # -------------------------------------------------------------
    if name in ("get_patient_appointments", "get_my_appointments", "get_upcoming_appointment"):
        filter_mode = args.get("filter", "upcoming" if name == "get_upcoming_appointment" else "all")

        if filter_mode == "all":
            appointments = await get_patient_appointments(context.patient_id, context.db)
            return {
                "ok": True,
                "appointments": [
                    {
                        "doctor_name": item.doctor.name,
                        "date": item.appointment_date.isoformat(),
                        "time": item.appointment_time.isoformat(timespec="minutes"),
                        "status": item.status,
                    }
                    for item in appointments
                ],
            }

        # Upcoming appointment lookup
        appointment = await get_upcoming_patient_appointment(context.patient_id, context.db)
        if appointment is None:
            return {"ok": True, "found": False}
        return {
            "ok": True,
            "found": True,
            "doctor_name": appointment.doctor.name,
            "date": appointment.appointment_date.isoformat(),
            "time": appointment.appointment_time.isoformat(timespec="minutes"),
            "status": appointment.status,
        }

    # -------------------------------------------------------------
    # 2. AVAILABILITY CHECK & BOOKING (Consolidated + Legacy)
    # -------------------------------------------------------------
    action = args.get("action")

    if name == "check_appointment_availability" or (name == "manage_appointment" and action == "check"):
        doctor_id = UUID(str(args["doctor_id"]))
        appointment_date = date.fromisoformat(str(args["appointment_date"]))
        logger.info("TOOL_CHECK_AVAILABILITY: doctor_id=%s date=%s user_text='%s'", doctor_id, appointment_date.isoformat(), context.user_text)
        availability = await get_doctor_availability(doctor_id, appointment_date, context.db)
        if availability is None:
            return {"ok": False, "error": "Doctor not found."}
        doctor, slots = availability
        return {
            "ok": True,
            "doctor": _doctor_data(doctor),
            "date": appointment_date.isoformat(),
            "available_slots": [slot.isoformat(timespec="minutes") for slot in slots],
        }

    if name == "book_appointment" or (name == "manage_appointment" and action == "book"):
        # Check if this is a confirmation call (no parameters provided, but we have pending booking)
        has_doctor_id = "doctor_id" in args and args["doctor_id"]
        has_date = "appointment_date" in args and args["appointment_date"]
        has_time = "appointment_time" in args and args["appointment_time"]
        
        logger.info(
            "TOOL_BOOK_APPOINTMENT: user_text='%s' is_conf=%s pending_exists=%s has_params=(doc=%s,date=%s,time=%s) args_keys=%s",
            context.user_text,
            _is_confirmation(context.user_text),
            context.session_id in _pending_bookings,
            has_doctor_id, has_date, has_time,
            list(args.keys())
        )
        
        # If confirmation is in user text and we have a pending booking, use it
        if _is_confirmation(context.user_text) and context.session_id in _pending_bookings and not (has_doctor_id and has_date and has_time):
            pending = _pending_bookings[context.session_id]
            doctor_id = pending.doctor_id
            appointment_date = pending.appointment_date
            appointment_time = pending.appointment_time
            logger.info("✓ CONFIRMATION_BOOKING using pending booking doctor_id=%s date=%s time=%s", doctor_id, appointment_date.isoformat(), appointment_time.isoformat(timespec="minutes"))
        else:
            # First call with parameters - validate and store
            if not has_doctor_id or not has_date:
                return {
                    "ok": False,
                    "error": "I could not understand the appointment details. Please provide doctor ID and appointment date.",
                }
            if not has_time:
                return {
                    "ok": False,
                    "error": "I could not understand the appointment time. Please provide the time.",
                }
            
            doctor_id = UUID(str(args["doctor_id"]))
            appointment_date = date.fromisoformat(str(args["appointment_date"]))
            appointment_time = time.fromisoformat(str(args["appointment_time"]))
            requested = PendingBooking(doctor_id, appointment_date, appointment_time)
            
            logger.info("FIRST_BOOKING_CALL: doctor_id=%s date=%s time=%s user_text='%s'", doctor_id, appointment_date.isoformat(), appointment_time.isoformat(timespec="minutes"), context.user_text)
            
            # Check if we have a DIFFERENT pending booking - don't overwrite unless user is confirming a NEW booking
            if context.session_id in _pending_bookings and not _is_confirmation(context.user_text):
                pending = _pending_bookings[context.session_id]
                logger.warning("NEW_BOOKING_ATTEMPT while pending exists: old_date=%s new_date=%s", pending.appointment_date.isoformat(), appointment_date.isoformat())
                # Clear the old pending booking and start fresh
                _pending_bookings.pop(context.session_id, None)

            if not _is_confirmation(context.user_text):
                # First call - require confirmation
                _pending_bookings[context.session_id] = requested
                return {
                    "ok": False,
                    "requires_confirmation": True,
                    "doctor_id": str(doctor_id),
                    "appointment_date": appointment_date.isoformat(),
                    "appointment_time": appointment_time.isoformat(timespec="minutes"),
                }

        # Confirmed booking - create the appointment
        appointment = await create_appointment(
            context.patient_id, doctor_id, appointment_date, appointment_time, context.db
        )
        await context.db.refresh(appointment, attribute_names=["doctor"])
        _pending_bookings.pop(context.session_id, None)
        logger.info("BOOKING_CONFIRMED: doctor_id=%s date=%s time=%s appointment_id=%s", doctor_id, appointment_date.isoformat(), appointment_time.isoformat(timespec="minutes"), appointment.id)
        return {
            "ok": True,
            "booked": True,
            "is_booking_success": True,
            "doctor_name": appointment.doctor.name,
            "date": appointment_date.isoformat(),
            "time": appointment_time.isoformat(timespec="minutes"),
            "appointment_id": str(appointment.id),  
            "status": appointment.status,
        }

    # -------------------------------------------------------------
    # 3. DOCUMENT Q&A
    # -------------------------------------------------------------
    if name == "patient_document_qa":
        answer = await answer_from_document(str(args["question"]), str(context.session_id))
        return {
            "ok": bool(answer.get("resolved")),
            "reply": answer.get("reply"),
            "source": answer.get("source"),
        }
    if name == "trigger_emergency_alert":
        current_patient = context.patient_id if context.patient_id else "GUEST_USER"
        logger.critical(f"EMERGENCY ALERT! Patient: {current_patient} | Symptom: {args.get('symptom_description')}")
        
        
        success = await send_twilio_sms("sms_appointment_reminders")
        
        if success:
            return {
                "ok": True,
                "alert_sent": True,
                "instruction": "Tell the user: 'I have immediately sent an emergency alert to the hospital. Please call 108 or go to the nearest emergency room right away.'"
            }
        else:
            return {
                "ok": False,
                "alert_sent": False,
                "instruction": "Tell the user: 'My system failed to contact the hospital automatically. This is a critical emergency. You must manually call 108 or go to the emergency room immediately.'"
            }

