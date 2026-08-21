"""
Answers a patient's question using ONLY their own uploaded documents,
with mandatory evidence (document, page, exact quoted snippet) so the
answer can be verified against the original — never blind trust.

Input:  question text + session_id
Output: {"reply": str, "resolved": bool, "language_code": str,
          "source": {"document": str, "page": int, "evidence": str} | None}
"""

import asyncio
import json
import os
from dotenv import load_dotenv
from groq import Groq
from .system_prompt import PATIENT_DOC_SYSTEM_PROMPT
from .retrieval import retrieve_relevant_chunks

load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY"))
MODEL = "openai/gpt-oss-20b"

NOT_FOUND_REPLY = (
    "I couldn't find that information in your uploaded document. "
    "You may not have uploaded a document yet, or it may not contain this information."
)
ERROR_REPLY = "Sorry, I had trouble reading your document just now. Please try again."


def _generate_document_content(user_content: str):
    """Run the synchronous Groq SDK call in a worker thread."""
    return client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "user", "content": user_content}
        ],
        temperature=0,
    )


async def answer_from_document(question: str, session_id: str) -> dict:
    if not question or not question.strip():
        return {"reply": "I didn't catch a question.", "resolved": False, "language_code": "en-US", "source": None}

    chunks = await retrieve_relevant_chunks(question, session_id)

    if not chunks:
        return {"reply": NOT_FOUND_REPLY, "resolved": False, "language_code": "en-US", "source": None}

    context_text = "\n\n".join(
        f"[Document: {c['document']}, Page {c['page']}]\n{c['text']}" for c in chunks
    )
    user_content = (
        f"{PATIENT_DOC_SYSTEM_PROMPT}\n\n"
        f"Retrieved excerpts from the patient's uploaded document:\n"
        f"----------------\n{context_text}\n----------------\n\n"
        f"Patient question:\n{question}"
    )

    response = await asyncio.to_thread(_generate_document_content, user_content)

    raw = (response.choices[0].message.content or "").strip()
    print(f"[patient_docs] raw Groq response: {raw!r}")

    try:
        data = json.loads(raw)
        if "reply" not in data or not str(data["reply"]).strip():
            raise ValueError("empty or missing reply field")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[patient_docs] parse/validation failed: {e}")
        data = {"reply": ERROR_REPLY, "resolved": False, "language_code": "en-US", "source": None}

    return data
