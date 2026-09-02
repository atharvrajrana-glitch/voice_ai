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
from ai_core.availability_service import cancel_appointment, create_appointment, get_doctor_availability , reschedule_appointment
from ai_core.doctor_service import get_all_doctors, get_doctors_by_department, get_doctors_by_specialization, get_doctors_by_name 
from ai_core.lab_report_service import get_latest_lab_report
from patient_docs.service import answer_from_document
from ai_core.notification import send_textbee_sms
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
_pending_cancellations: dict[UUID, dict] = {}
_pending_reschedules: dict[UUID, PendingReschedule] = {}

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
            "Manage appointment operations. Use action='check' to check available slots on a date, action='book' to finalize booking after user confirms, or action='cancel' to cancel an existing appointment using its appointment_id.",
            {
                "action": {"type": "string", "enum": ["check", "book", "cancel", "reschedule"]},                
                "doctor_id": {"type": "string", "description": "Doctor UUID (required for 'check' and 'book')"},
                "appointment_id": {"type": "string", "description": "Appointment UUID to reschedule (required for 'reschedule')"},
                "appointment_date": {"type": "string", "format": "date", "description": f"For check/book/cancel: the target date. For reschedule: the NEW date. Today is {today.isoformat()}; use future dates only."},
                "appointment_time": {"type": "string", "nullable": True, "description": "HH:MM. Required for book and reschedule. Pass null for check and cancel."},
                "old_appointment_date": {"type": "string", "format": "date", "nullable": True, "description": "Required only for reschedule: the date of the EXISTING appointment being moved."}
            },
            ["action"]
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
        _groq_tool(
            "check_lab_report",
            "check whether the authenticated patient's lab report is ready , and get a summary if so. Never accept a patient ID.",
            {},
        )
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
        elif name =="check_lab_report":
            session_error = _needs_session(context)
            if session_error :
                return session_error
            
            report =await get_latest_lab_report(str(context.patient_id), context.db)
            if not report:
                result = {"ok":True,"found":False,"message":"No lab report found for this patient"}
            else:
                result = {
                    "ok":True,
                    "found":True,
                    "status":report.report_status,
                    "summary": report.report_summary if report.report_status =="ready" else None,
                }
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
                        "appointment_id": str(item.id),
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
    if name == "manage_appointment" and action == "reschedule":
        session_error = _needs_session(context)
        if session_error:
            return session_error

        has_appointment_id = "appointment_id" in args and args["appointment_id"]
        has_new_date = "appointment_date" in args and args["appointment_date"]
        has_new_time = "appointment_time" in args and args["appointment_time"]

        logger.info(
            "TOOL_RESCHEDULE_APPOINTMENT: user_text='%s' is_conf=%s pending_exists=%s has_params=(id=%s,date=%s,time=%s)",
            context.user_text,
            _is_confirmation(context.user_text),
            context.session_id in _pending_reschedules,
            has_appointment_id, has_new_date, has_new_time,
        )

        # If NOT confirmation - validate and store
        if not _is_confirmation(context.user_text):
            if not has_appointment_id:
                return {"ok": False, "error": "Please check your appointments first using get_patient_appointments, then provide the appointment_id."}
            if not has_new_date or not has_new_time:
                return {"ok": False, "error": "Please provide new date and time."}

            # Get old appointment details for confirmation message
            result = await context.db.execute(
                select(Appointment).where(
                    Appointment.id == UUID(str(args["appointment_id"])),
                    Appointment.patient_id == context.patient_id,
                    Appointment.status == "scheduled"
                )
            )
            old_appointment = result.scalar_one_or_none()
            
            if not old_appointment:
                return {"ok": False, "error": "Appointment not found."}

            # Store pending reschedule
            _pending_reschedules[context.session_id] = {
                "appointment_id": UUID(str(args["appointment_id"])),
                "old_date": old_appointment.appointment_date,
                "old_time": old_appointment.appointment_time,
                "new_date": date.fromisoformat(str(args["appointment_date"])),
                "new_time": time.fromisoformat(str(args["appointment_time"]))
            }

            return {
                "ok": False,
                "requires_confirmation": True,
                "instruction": "Ask the patient to confirm they want to reschedule this appointment before proceeding.",
                "old_date": old_appointment.appointment_date.isoformat(),
                "old_time": old_appointment.appointment_time.isoformat(timespec="minutes"),
                "new_date": date.fromisoformat(str(args["appointment_date"])).isoformat(),
                "new_time": time.fromisoformat(str(args["appointment_time"])).isoformat(timespec="minutes"),
            }

        # If confirmation - execute reschedule
        pending = _pending_reschedules.get(context.session_id)
        if not pending:
            return {"ok": False, "error": "No pending reschedule found. Please provide appointment details again."}

        # Call reschedule function
        appointment = await reschedule_appointment(
            context.patient_id,
            pending["appointment_id"],
            pending["new_date"],
            pending["new_time"],
            context.db
        )

        _pending_reschedules.pop(context.session_id, None)

        if not appointment:
            return {"ok": False, "error": "Could not reschedule appointment."}

        logger.info("RESCHEDULE_CONFIRMED: appointment_id=%s old_date=%s old_time=%s new_date=%s new_time=%s doctor=%s", 
                    pending["appointment_id"], 
                    pending["old_date"].isoformat(), 
                    pending["old_time"].isoformat(timespec="minutes"),
                    appointment.appointment_date.isoformat(),
                    appointment.appointment_time.isoformat(timespec="minutes"),
                    appointment.doctor.name)

        return {
            "ok": True,
            "rescheduled": True,
            "doctor_name": appointment.doctor.name,
            "old_date": pending["old_date"].isoformat(),
            "old_time": pending["old_time"].isoformat(timespec="minutes"),
            "new_date": appointment.appointment_date.isoformat(),
            "new_time": appointment.appointment_time.isoformat(timespec="minutes"),
        }

    if name == "manage_appointment" and action == "cancel":
        session_error = _needs_session(context)
        if session_error:
            return session_error
        has_appointment_id = "appointment_id" in args and args["appointment_id"]

        logger.info(
            "TOOL_CANCEL_APPOINTMENT: user_text='%s' is_conf=%s has_appointment_id=%s",
            context.user_text,
            _is_confirmation(context.user_text),
            has_appointment_id,
        )
        
        if not has_appointment_id:
            return {
                "ok": False,
                "error": "Please check your appointments first using get_patient_appointments, then provide the appointment_id to cancel.",
            }
        
        appointment_id = UUID(str(args["appointment_id"]))
        
        # Store pending cancellation with just the appointment_id
        if not _is_confirmation(context.user_text):
            # First call - ask for confirmation
            _pending_cancellations[context.session_id] = {"appointment_id": appointment_id}
            return {
                "ok": False,
                "requires_confirmation": True,
                "instruction": "Ask the patient to confirm they want to cancel this appointment before proceeding.",
            }
        
        # Confirmed - execute cancellation
        appointment = await cancel_appointment(context.patient_id, appointment_id, context.db)
        _pending_cancellations.pop(context.session_id, None)
        
        if appointment is None:
            return {"ok": False, "error": "No appointment found with that ID, or it's already cancelled."}
        
        logger.info("CANCELLATION_CONFIRMED: appointment_id=%s doctor=%s date=%s", appointment_id, appointment.doctor.name, appointment.appointment_date.isoformat())
        return {
            "ok": True,
            "cancelled": True,
            "doctor_name": appointment.doctor.name,
            "appointment_date": appointment.appointment_date.isoformat(),
            "appointment_time": appointment.appointment_time.isoformat(timespec="minutes"),
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
        current_patient_id = context.patient_id if context.patient_id else "GUEST_USER"
        symptom = args.get('symptom_description', 'Unknown critical symptom')
        
        logger.critical(f"EMERGENCY ALERT! Patient ID: {current_patient_id} | Symptom: {symptom}")
        
        # Defaults
        patient_phone = None
        patient_name = "Unknown Patient (Guest)"
        
        # Get patient's phone number AND name from database
        if context.patient_id:
            # ✅ FIX: Use context.db instead of just db
            patient = await context.db.get(Patient, context.patient_id)
            if patient:
                patient_phone = patient.phone
                patient_name = patient.name 
        
        if not patient_phone:
            return {
                "ok": False,
                "alert_sent": False,
                "instruction": "Tell the user: 'Unable to verify your phone number. Please manually call 108 or go to the nearest emergency room immediately.'"
            }
        
        # Format the dynamic SMS body
        alert_message = (
            f"🚨 EMERGENCY ALERT from MedClear 🚨\n"
            f"A patient requires immediate attention.\n"
            f"Please log into the secure MedClear dashboard to view patient details."
        )
        
        success = await send_textbee_sms(
            body=alert_message,
            phone_number=patient_phone
        )
        
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