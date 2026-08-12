"""
The AI core service — running on Gemini 3.5 Flash.

Input:  plain text (what the patient said, transcribed by Module 1)
Output: {"reply": str, "resolved": bool, "language": str}

Nothing outside this file needed to change to make this swap — that's
the point of keeping the AI provider isolated to one module.
"""

import json
import os
from google import genai
from google.genai import types
from .system_prompt import SYSTEM_PROMPT

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

MODEL = "gemini-3.5-flash"

FALLBACK_REPLY = "Sorry, I wasn't able to work out an answer to that. Could you try asking again?"


def get_ai_response(patient_text: str) -> dict:
    if not patient_text or not patient_text.strip():
        return {"reply": "I didn't catch that. Could you say it again?", "resolved": False, "language": "unknown"}

    response = client.models.generate_content(
        model=MODEL,
        contents=patient_text,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            # Force strict JSON output instead of relying on the prompt
            # alone — this stops the model from ever returning malformed
            # or partial JSON.
            response_mime_type="application/json",
        ),
    )

    raw = (response.text or "").strip()

    # Debug log — check this terminal if replies ever come back empty
    # again, so we can see exactly what the model actually sent.
    print(f"[ai_core] raw Gemini response: {raw!r}")

    try:
        data = json.loads(raw)
        if "reply" not in data or not str(data["reply"]).strip():
            raise ValueError("empty or missing reply field")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[ai_core] parse/validation failed: {e}")
        data = {"reply": FALLBACK_REPLY, "resolved": False, "language": "unknown"}

    return data