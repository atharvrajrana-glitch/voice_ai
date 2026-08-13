"""
The AI core service — running on Gemini 3.5 Flash, now optionally
grounded in retrieved hospital policy context (RAG).

Input:  plain text (what the patient said, transcribed by Module 1)
Output: {"reply": str, "resolved": bool, "language": str, "sources": list}

Retrieval failures never crash this — if the vector store has nothing
relevant (or errors), the AI core just answers using its own knowledge
and the same rules as before, exactly like it did before RAG existed.
"""

import json
import os
from google import genai
from google.genai import types
from .system_prompt import SYSTEM_PROMPT
from RAG.retrieval import retrieve_hospital_context

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

MODEL = "gemini-3.5-flash"

FALLBACK_REPLY = "Sorry, I wasn't able to work out an answer to that. Could you try asking again?"


def get_ai_response(patient_text: str) -> dict:
    if not patient_text or not patient_text.strip():
        return {"reply": "I didn't catch that. Could you say it again?", "resolved": False, "language": "unknown", "sources": []}

    context, sources = retrieve_hospital_context(patient_text)

    if context:
        user_content = (
            f"Hospital-specific reference information (use this if it's "
            f"relevant to the question; ignore it if it's not):\n"
            f"----------------\n{context}\n----------------\n\n"
            f"Patient question:\n{patient_text}"
        )
    else:
        user_content = patient_text

    response = client.models.generate_content(
        model=MODEL,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )

    raw = (response.text or "").strip()
    print(f"[ai_core] raw Gemini response: {raw!r}")

    try:
        data = json.loads(raw)
        if "reply" not in data or not str(data["reply"]).strip():
            raise ValueError("empty or missing reply field")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[ai_core] parse/validation failed: {e}")
        data = {"reply": FALLBACK_REPLY, "resolved": False, "language": "unknown"}

    data["sources"] = sources
    return data 