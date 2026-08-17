"""
Module 2 backend — the AI core, exposed as an API.

Run with:
    uvicorn main:app --reload --port 8001

The frontend (Module 1's voice loop, or the standalone test UI) calls
POST /api/ai-core with { "text": "..." } and gets back
{ "reply": "...", "resolved": true/false, "language": "..." }
"""

import asyncio
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai_core.service import get_ai_response, _validate_and_refresh_session
from patient_docs.ingest import ingest_pdf
from patient_docs.service import answer_from_document

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, get_db
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
from routers.patients import router as patients_router
from routers.sessions import router as sessions_router
from routers.appointments import router as appointments_router
from routers.doctors import router as doctors_router

app = FastAPI(title="MedClear AI Core")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    text: str
    document_mode: bool = False

class PatientDocQARequest(BaseModel):
    question: str
    session_id: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/ai-core")
async def ai_core_endpoint(
    req: QueryRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db),
):
    session = None
    if x_session_id:
        try:
            session = await _validate_and_refresh_session(UUID(x_session_id), db)
        except (ValueError, TypeError):
            session = None

    # A PDF is actively attached in the Voice Assistant. Answer it directly
    # instead of first asking Gemini to select a tool and then asking it again
    # to format the tool result. This removes two serial model round-trips.
    if req.document_mode and session:
        try:
            answer = await asyncio.to_thread(answer_from_document, req.text, str(session.id))
            return {
                "reply": answer.get("reply", "Sorry, I had trouble reading your document just now. Please try again."),
                "resolved": bool(answer.get("resolved", False)),
                "language": answer.get("language") or answer.get("language_code", "English"),
                "sources": [answer["source"]] if answer.get("source") else [],
            }
        except Exception:
            return {
                "reply": "Sorry, I had trouble reading your document just now. Please try again.",
                "resolved": False,
                "language": "English",
                "sources": [],
            }
    return await get_ai_response(
        req.text,
        session_id=session.id if session else None,
        patient_id=session.patient_id if session else None,
        db=db,
    )


@app.post("/api/patient-doc/upload")
async def patient_doc_upload_endpoint(file: UploadFile = File(...), session_id: str = Form(...)):
    file_bytes = await file.read()
    return ingest_pdf(file_bytes, file.filename, session_id)


@app.post("/api/patient-doc/ask")
def patient_doc_ask_endpoint(req: PatientDocQARequest):
    return answer_from_document(req.question, req.session_id)

@app.get("/health/db")
async def database_health():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT 1"))
        return {
            "database": "connected",
            "result": result.scalar()
        }
    
app.include_router(patients_router)
app.include_router(sessions_router)
app.include_router(appointments_router)
app.include_router(doctors_router)
