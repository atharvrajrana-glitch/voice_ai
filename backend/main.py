"""
Module 2 backend — the AI core, exposed as an API.

Run with:
    uvicorn main:app --reload --port 8080
"""

import asyncio
import json
import logging
import os
import re
import sys
from typing import Optional
from uuid import UUID

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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

app = FastAPI(title="MedClear AI Core")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Redis client
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

class QueryRequest(BaseModel):
    text: str
    document_mode: bool = False
    stream: bool = False

class PatientDocQARequest(BaseModel):
    question: str
    session_id: str


def get_cache_info(user_text: str, patient_id: str | None, session_id: str | None):
    """Analyzes text to return the correct Redis key and TTL."""
    clean_text = re.sub(r'[^\w\s]', '', user_text.lower()).strip()
    
    personal_keywords = {"my", "i", "me", "mine", "appointment", "report", "bill", "cancel", "book"}
    words = set(clean_text.split())
    
    is_personal = bool(words.intersection(personal_keywords))
    identifier = patient_id or session_id or "anonymous"
    
    if is_personal:
        cache_key = f"medclear_cache:user:{identifier}:{clean_text}"
        ttl = 60
    else:
        cache_key = f"medclear_cache:global:{clean_text}"
        ttl = 86400
        
    return cache_key, ttl


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

    # Handle attached PDF document questions directly
    if req.document_mode and session:
        try:
            answer = await answer_from_document(req.text, str(session.id))
            reply_text = answer.get("reply", "Sorry, I had trouble reading your document just now. Please try again.")
            resolved = bool(answer.get("resolved", False))
            language = answer.get("language") or answer.get("language_code", "English")
            sources = [answer["source"]] if answer.get("source") else []
        except Exception:
            reply_text = "Sorry, I had trouble reading your document just now. Please try again."
            resolved = False
            language = "English"
            sources = []

        if req.stream:
            async def doc_event_generator():
                # STRUCTURED JSON: Prevents the browser from stripping spaces
                payload = json.dumps({"text": reply_text})
                yield f"data: {payload}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(doc_event_generator(), media_type="text/event-stream")

        return {"reply": reply_text, "resolved": resolved, "language": language, "sources": sources}

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

            # Try Cache First
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
                
                if full_response.strip():
                    try:
                        await redis_client.setex(cache_key, ttl, full_response.strip())
                    except Exception as e:
                        ai_core_logger.warning(f"Redis write error: {e}")

            except Exception as e:
                yield f"data: [ERROR] {str(e)}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # 2. STANDARD JSON RESPONSE WITH CACHE
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
    
    if response_data.get("resolved"):
        try:
            await redis_client.setex(cache_key, ttl, response_data["reply"])
        except Exception as e:
            ai_core_logger.warning(f"Redis write error: {e}")
            
    return response_data

@app.post("/api/patient-doc/upload")
async def patient_doc_upload_endpoint(file: UploadFile = File(...), session_id: str = Form(...)):
    file_bytes = await file.read()
    return await ingest_pdf(file_bytes, file.filename, session_id)

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
