"""
Module 2 backend — the AI core, exposed as an API.

Run with:
    uvicorn main:app --reload --port 8001

The frontend (Module 1's voice loop, or the standalone test UI) calls
POST /api/ai-core with { "text": "..." } and gets back
{ "reply": "...", "resolved": true/false, "language": "..." }
"""

import sys
import os

# The RAG folder lives at the project root (a sibling of backend/, not
# inside it), so add the project root to Python's search path before
# anything tries to import it. This must happen before the ai_core
# import below, since that's what triggers "from RAG.retrieval import".
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai_core.service import get_ai_response
from patient_docs.ingest import ingest_pdf
from patient_docs.service import answer_from_document

app = FastAPI(title="MedClear AI Core")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:5\d{3}",
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    text: str




class PatientDocQARequest(BaseModel):
    question: str
    session_id: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/ai-core")
def ai_core_endpoint(req: QueryRequest):
    return get_ai_response(req.text)


@app.post("/api/patient-doc/upload")
async def patient_doc_upload_endpoint(file: UploadFile = File(...), session_id: str = Form(...)):
    file_bytes = await file.read()
    return ingest_pdf(file_bytes, file.filename, session_id)


@app.post("/api/patient-doc/ask")
def patient_doc_ask_endpoint(req: PatientDocQARequest):
    return answer_from_document(req.question, req.session_id)