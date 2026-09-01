"""
Module 2 backend — the AI core, exposed as an API.

Run with:
    uvicorn backend.main:app --reload --port 8080
"""

import os
import sys

# CRITICAL: Add backend and workspace root to sys.path FIRST
# This allows all imports (ai_core, app, patient_docs, etc) to work
backend_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.dirname(backend_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)
 
import asyncio
import json
import logging
import re
from typing import Optional
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()

# Logger setup
ai_core_logger = logging.getLogger("ai_core")
ai_core_logger.setLevel(logging.INFO)
if not ai_core_logger.handlers:
    timing_handler = logging.StreamHandler()
    timing_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    ai_core_logger.addHandler(timing_handler)
ai_core_logger.propagate = False

from fastapi import Depends, FastAPI, File, Form, Header, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis


from ai_core.service import (
    _validate_and_refresh_session,
    get_ai_response,
    stream_ai_response,
)
from app.core.database import AsyncSessionLocal, get_db
from patient_docs.ingest import ingest_pdf
from patient_docs.service import answer_from_document
from routers.sessions import router as sessions_router
from RAG.ingest import ingest_documents
from ai_core.availability_service import mark_past_appointments_done


def rich_transcription_postprocess(text: str) -> str:
    """Simple postprocessing for transcription - can be expanded"""
    return text.strip() if text else ""

app = FastAPI(title="MedClear AI Core")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Redis client
redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)

@app.on_event("startup")
async def startup_event():
    """Run database migrations, ingest hospital documents, and load transcription model on startup."""
    try:
        # Run database migrations
        ai_core_logger.info("Running database migrations...")
        import subprocess
        import os
        
        # Get the backend directory
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Run alembic migrations
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=backend_dir,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            ai_core_logger.info("Database migrations completed successfully.")
        else:
            ai_core_logger.warning(f"Migration output: {result.stderr}")
    except Exception as e:
        ai_core_logger.warning(f"Failed to run migrations: {e}")
        # Don't fail startup if migrations fail
    
    try:
        ai_core_logger.info("Starting RAG document ingestion...")
        await ingest_documents()
        ai_core_logger.info("RAG document ingestion completed successfully.")
    except Exception as e:
        ai_core_logger.error(f"Failed to ingest RAG documents: {e}")
        # Don't fail startup if ingestion fails - system can still work without RAG
    
    try:
        ai_core_logger.info("Marking past appointments as done...")
        async with AsyncSessionLocal() as db:
            count = await mark_past_appointments_done(db)
            ai_core_logger.info(f"Marked {count} past appointments as done.")
    except Exception as e:
        ai_core_logger.warning(f"Failed to mark past appointments: {e}")
        # Don't fail startup if this fails
    
    

class QueryRequest(BaseModel):
    text: str
    document_mode: bool = False
    stream: bool = False

class PatientDocQARequest(BaseModel):
    question: str
    session_id: str


def get_cache_info(user_text: str, patient_id: str | None, session_id: str | None) -> tuple[str | None, int]:
    """Analyzes text to return the correct Redis key and TTL, or (None, 0) to skip caching entirely."""
    clean_text = re.sub(r'[^\w\s]', '', user_text.lower()).strip()
    words = set(clean_text.split())

    # Never cache short/ambiguous replies — these are almost always mid-conversation
    # (confirmations, doctor names, dates, single-word answers) and their correct
    # response depends entirely on prior conversation context, not the text alone.
    if len(words) <= 3:
        return None, 0

    personal_keywords = {"my", "i", "me", "mine", "appointment", "report", "bill", "cancel", "book"}
    is_personal = bool(words.intersection(personal_keywords))
    identifier = patient_id or session_id or "anonymous"

    if is_personal:
        # Personal/contextual questions must be scoped per-user, never shared globally
        cache_key = f"medclear_cache:user:{identifier}:{clean_text}"
        ttl = 60
    else:
        cache_key = f"medclear_cache:global:{clean_text}"
        ttl = 86400

    return cache_key, ttl


def is_emergency_request(user_text: str) -> bool:
    """Emergency requests must bypass Redis and always reach the alert tool."""
    normalized = re.sub(r"[^\w\s]", " ", user_text.lower())
    emergency_phrases = (
        "chest pain", "heart attack", "stroke", "severe bleeding",
        "cant breathe", "cannot breathe", "difficulty breathing",
        "emergency", "unconscious",
    )
    return any(phrase in normalized for phrase in emergency_phrases)


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

    session_id = session.id if session else None
    patient_id = session.patient_id if session else None
    
    # Force document_mode ON if documents exist for this session
    # This handles the case where frontend uploadStatus tracking fails
    documents_available = False
    if session_id:
        try:
            # Quick check: do we have any chunks for this session?
            from patient_docs.vector_store import collection
            results = collection.get(
                where={"session_id": str(session_id)},
                limit=1
            )
            documents_available = len(results.get("ids", [])) > 0
            if documents_available:
                ai_core_logger.info(f"DOCUMENTS_DETECTED: session_id={session_id}, forcing document_mode=True")
        except Exception as e:
            ai_core_logger.warning(f"Could not check for documents: {e}")
    
    # Override document_mode if documents exist
    document_mode = req.document_mode or documents_available
    
    ai_core_logger.info(f"REQUEST: document_mode={document_mode} (requested={req.document_mode}, detected={documents_available}) stream={req.stream} session_id={session_id} text='{req.text[:60]}'")

    if document_mode and session:
        ai_core_logger.info(f"DOCUMENT_MODE_ACTIVE: retrieving from document for session_id={session.id}")
        try:
            answer = await answer_from_document(req.text, str(session.id))
            reply_text = answer.get("reply", "Sorry, I had trouble reading your document just now. Please try again.")
            resolved = bool(answer.get("resolved", False))
            language = answer.get("language") or answer.get("language_code", "en")
            sources = [answer["source"]] if answer.get("source") else []
            ai_core_logger.info(f"DOCUMENT_ANSWER_SUCCESS: reply='{reply_text[:60]}' resolved={resolved}")
        except Exception as e:
            ai_core_logger.exception(f"DOCUMENT_MODE_ERROR: {e}")
            reply_text = None
            resolved = False
            language = "en"
            sources = []

        if resolved:
            if req.stream:
                async def doc_event_generator():
                    payload = json.dumps({"text": reply_text})
                    yield f"data: {payload}\n\n"
                    yield "data: [DONE]\n\n"
                return StreamingResponse(doc_event_generator(), media_type="text/event-stream")

            return {"reply": reply_text, "resolved": resolved, "language": language, "sources": sources}

        ai_core_logger.info("DOCUMENT_ANSWER_NOT_FOUND: falling back to general assistant flow")

    emergency_request = is_emergency_request(req.text)
    cache_key, ttl = get_cache_info(
        user_text=req.text, 
        patient_id=str(patient_id) if patient_id else None, 
        session_id=str(session_id) if session_id else None
    )

    # 1. STREAMING RESPONSE WITH CACHE
    if req.stream:
        async def event_generator():
            
            # --- HELPER: Forces structured word-by-word streaming ---
            async def smooth_stream(text_chunk):
                parts = re.split(r'(\s+)', text_chunk)
                for part in parts:
                    if part:
                        # STRUCTURED JSON: Wraps every word/space safely
                        payload = json.dumps({"text": part})
                        yield f"data: {payload}\n\n"
                        await asyncio.sleep(0.02) 

            # Emergency responses are never cached: the alert tool must run each time.
            if not emergency_request and cache_key:
                try:
                    cached_reply = await redis_client.get(cache_key)
                    if cached_reply:
                        ai_core_logger.info(f"ai_cache_hit text='{req.text}' type={'personal' if ttl == 60 else 'global'}")
                        async for frame in smooth_stream(cached_reply):
                            yield frame
                        yield "data: [DONE]\n\n"
                        return
                except Exception as e:
                    ai_core_logger.warning(f"Redis read error: {e}")

            # Cache Miss: Stream from Gemini
            ai_core_logger.info(f"ai_cache_miss text='{req.text}'")
            full_response = ""
            try:
                async for chunk in stream_ai_response(
                    patient_text=req.text,
                    session_id=session_id,
                    patient_id=patient_id,
                    db=db,
                ):
                    safe_chunk = chunk.replace("\n", " ")
                    full_response += safe_chunk
                    
                    async for frame in smooth_stream(safe_chunk):
                        yield frame
                
                yield "data: [DONE]\n\n"
                
                if full_response.strip() and not emergency_request and cache_key:
                    try:
                        await redis_client.setex(cache_key, ttl, full_response.strip())
                    except Exception as e:
                        ai_core_logger.warning(f"Redis write error: {e}")

            except Exception as e:
                yield f"data: [ERROR] {str(e)}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # 2. STANDARD JSON RESPONSE WITH CACHE
    if not emergency_request:
        try:
            cached_reply = await redis_client.get(cache_key)
            if cached_reply:
                ai_core_logger.info(f"ai_cache_hit text='{req.text}' type={'personal' if ttl == 60 else 'global'}")
                return {
                    "reply": cached_reply,
                    "resolved": True,
                    "language": "en",
                    "sources": []
                }
        except Exception as e:
            ai_core_logger.warning(f"Redis read error: {e}")

    ai_core_logger.info(f"ai_cache_miss text='{req.text}'")
    response_data = await get_ai_response(
        req.text,
        session_id=session_id,
        patient_id=patient_id,
        db=db,
    )
    
    if response_data.get("resolved") and not emergency_request:
        try:
            await redis_client.setex(cache_key, ttl, response_data["reply"])
        except Exception as e:
            ai_core_logger.warning(f"Redis write error: {e}")
            
    return response_data

@app.post("/api/patient-doc/upload")
async def patient_doc_upload_endpoint(file: UploadFile = File(...), session_id: str = Form(...)):
    file_bytes = await file.read()
    ai_core_logger.info(f"UPLOAD_START: file={file.filename} session_id={session_id} size={len(file_bytes)}")
    result = await ingest_pdf(file_bytes, file.filename, session_id)
    return result

@app.post("/api/patient-doc/ask")
async def patient_doc_ask_endpoint(req: PatientDocQARequest):
    return await answer_from_document(req.question, req.session_id)

@app.get("/health/db")
async def database_health():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT 1"))
        return {
            "database": "connected",
            "result": result.scalar(),
        }

app.include_router(sessions_router)



        

