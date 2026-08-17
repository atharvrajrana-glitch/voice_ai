"""Gemini tool declarations and trusted in-process tool dispatch."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, time
from typing import Any
from uuid import UUID

from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from RAG.retrieval import retrieve_hospital_context
from ai_core.availability_service import create_appointment, get_doctor_availability
from ai_core.doctor_service import get_all_doctors, get_doctors_by_department, get_doctors_by_specialization
from patient_docs.service import answer_from_document

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolContext:
    """Trusted data derived from the HTTP request, never Gemini arguments."""

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


def _declaration(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> types.FunctionDeclaration:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return types.FunctionDeclaration(name=name, description=description, parameters_json_schema=schema)


def get_gemini_tools() -> list[types.Tool]:
    declarations = [
        _declaration("search_hospital", "Search hospital policies, facilities, billing, insurance, pharmacy, departments, or visiting hours. Do not use for patient-specific data.", {"question": {"type": "string"}}, ["question"]),
        _declaration("get_my_appointments", "Get appointments for the authenticated patient. Never accept a patient ID.", {}),
        _declaration("get_upcoming_appointment", "Get the authenticated patient's next appointment. Never accept a patient ID.", {}),
        _declaration("find_doctors", "Find doctors by department or specialization.", {"department": {"type": "string"}, "specialization": {"type": "string"}}),
        _declaration("check_appointment_availability", "Check a doctor's available slots on a date before offering or booking a time.", {"doctor_id": {"type": "string", "description": "A doctor UUID returned by find_doctors."}, "appointment_date": {"type": "string", "format": "date", "description": "YYYY-MM-DD"}}, ["doctor_id", "appointment_date"]),
        _declaration("book_appointment", "Create an appointment only after the patient explicitly confirms the exact doctor, date, and time. Never accept a patient ID.", {"doctor_id": {"type": "string"}, "appointment_date": {"type": "string", "format": "date"}, "appointment_time": {"type": "string", "description": "HH:MM in 24-hour format"}}, ["doctor_id", "appointment_date", "appointment_time"]),
        _declaration("patient_document_qa", "Answer a question about the authenticated patient's uploaded document. Never accept a patient ID or document content.", {"question": {"type": "string"}}, ["question"]),
    ]
    return [types.Tool(function_declarations=declarations)]


def _needs_session(context: ToolContext) -> dict[str, Any] | None:
    if context.session_id is None or context.patient_id is None:
        return {"ok": False, "error": "Please sign in before accessing your appointment or document information."}
    return None


def _doctor_data(doctor: Any) -> dict[str, str]:
    return {"id": str(doctor.id), "name": doctor.name, "specialization": doctor.specialization, "department": doctor.department}


def _is_confirmation(text: str) -> bool:
    return " ".join(text.lower().strip().split()).strip(".!?,") in {"yes", "yes please", "confirm", "confirm it", "book it", "yes book it", "go ahead", "please proceed"}


async def execute_tool(name: str, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Run only allow-listed tools and return minimal JSON-safe values."""
    try:
        logger.info("TOOL_SELECTED: %s", name)
        if name == "search_hospital":
            hospital_context, sources = retrieve_hospital_context(str(args["question"]).strip())
            result = {"ok": bool(hospital_context), "context": hospital_context or "", "sources": sources}
        elif name == "find_doctors":
            department = str(args.get("department") or "").strip()
            specialization = str(args.get("specialization") or "").strip()
            if department:
                doctors = await get_doctors_by_department(department, context.db)
            elif specialization:
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

    if name == "get_my_appointments":
        appointments = await get_patient_appointments(context.patient_id, context.db)
        return {"ok": True, "appointments": [{"doctor_name": item.doctor.name, "date": item.appointment_date.isoformat(), "time": item.appointment_time.isoformat(timespec="minutes"), "status": item.status} for item in appointments]}
    if name == "get_upcoming_appointment":
        appointment = await get_upcoming_patient_appointment(context.patient_id, context.db)
        if appointment is None:
            return {"ok": True, "found": False}
        return {"ok": True, "found": True, "doctor_name": appointment.doctor.name, "date": appointment.appointment_date.isoformat(), "time": appointment.appointment_time.isoformat(timespec="minutes"), "status": appointment.status}
    if name == "check_appointment_availability":
        doctor_id = UUID(str(args["doctor_id"]))
        appointment_date = date.fromisoformat(str(args["appointment_date"]))
        availability = await get_doctor_availability(doctor_id, appointment_date, context.db)
        if availability is None:
            return {"ok": False, "error": "Doctor not found."}
        doctor, slots = availability
        return {"ok": True, "doctor": _doctor_data(doctor), "date": appointment_date.isoformat(), "available_slots": [slot.isoformat(timespec="minutes") for slot in slots]}
    if name == "book_appointment":
        doctor_id = UUID(str(args["doctor_id"]))
        appointment_date = date.fromisoformat(str(args["appointment_date"]))
        appointment_time = time.fromisoformat(str(args["appointment_time"]))
        requested = PendingBooking(doctor_id, appointment_date, appointment_time)
        if _pending_bookings.get(context.session_id) != requested or not _is_confirmation(context.user_text):
            _pending_bookings[context.session_id] = requested
            return {"ok": False, "requires_confirmation": True, "date": appointment_date.isoformat(), "time": appointment_time.isoformat(timespec="minutes"), "instruction": "Ask the patient to explicitly confirm these exact details. Do not say it is booked."}
        appointment = await create_appointment(context.patient_id, doctor_id, appointment_date, appointment_time, context.db)
        await context.db.refresh(appointment, attribute_names=["doctor"])
        _pending_bookings.pop(context.session_id, None)
        return {"ok": True, "booked": True, "doctor_name": appointment.doctor.name, "date": appointment.appointment_date.isoformat(), "time": appointment.appointment_time.isoformat(timespec="minutes"), "status": appointment.status}
    if name == "patient_document_qa":
        answer = answer_from_document(str(args["question"]), str(context.session_id))
        return {"ok": bool(answer.get("resolved")), "reply": answer.get("reply"), "source": answer.get("source")}
    return {"ok": False, "error": "That action is unavailable."}
