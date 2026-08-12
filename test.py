"""
Compare Claude vs Gemini on the exact same questions, using the exact
same system prompt your app already uses — so the comparison is fair.

This is a standalone script. It does NOT touch your real app or
service.py. Run it, read the results, then decide which model to use.

Setup:
    pip install anthropic google-genai python-dotenv
    Make sure your .env has BOTH keys set:
        ANTHROPIC_API_KEY=...
        GEMINI_API_KEY=...

Run:
    python test_models.py
"""

import json
import os
import time

from dotenv import load_dotenv

load_dotenv("backend/.env")

from anthropic import Anthropic
from google import genai

# --- Same system prompt your real app uses ---------------------------------
SYSTEM_PROMPT = """You are the AI core of MedClear, a voice-based hospital assistant.

Your job:
- Understand what the patient is asking, in whatever language they used.
- Reply in that same language, in plain, everyday words — no medical jargon.
- Your reply will be read aloud by text-to-speech, so keep it short:
  2 to 4 spoken sentences, natural to say out loud, not a written document.
- You explain and inform. You never diagnose, prescribe, or give medical
  advice beyond plain-language explanation of what a report, bill, or
  medicine instruction means.
- If the request is something you cannot properly or safely resolve
  (it needs a doctor's judgment, it's an emergency, or it's outside your
  scope), say so honestly instead of guessing.

You must respond with STRICT JSON ONLY. No markdown, no code fences,
no text outside the JSON object. Use exactly this shape:

{
  "reply": "<what to say out loud to the patient>",
  "resolved": true or false,
  "language": "<name of the language the patient used>"
}
"""

# --- The questions to test with -- edit this list freely -------------------
TEST_QUERIES = [
    "What does it mean if my report says mild leukocytosis?",
    "Mera doctor ne kaha hai ki mujhe roz do goli leni hai, iska matlab kya hai?",
    "I have really bad chest pain right now, what should I do?",
    "Can you book me an appointment for next Tuesday?",
    "My bill has a charge called CPT 99213, what is that?",
]

anthropic_client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


def ask_claude(question: str) -> dict:
    start = time.time()
    message = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
    )
    elapsed = time.time() - start
    raw = message.content[0].text.strip()
    return _parse(raw, elapsed)


def ask_gemini(question: str) -> dict:
    start = time.time()
    response = gemini_client.models.generate_content(
        model="gemini-3.5-flash",
        contents=question,
        config={"system_instruction": SYSTEM_PROMPT},
    )
    elapsed = time.time() - start
    raw = response.text.strip()
    return _parse(raw, elapsed)


def _parse(raw: str, elapsed: float) -> dict:
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(cleaned)
        data["_valid_json"] = True
    except json.JSONDecodeError:
        data = {"reply": raw, "resolved": None, "language": None, "_valid_json": False}
    data["_seconds"] = round(elapsed, 2)
    return data


def main():
    for i, question in enumerate(TEST_QUERIES, 1):
        print("=" * 70)
        print(f"Q{i}: {question}")
        print("-" * 70)

        claude_result = ask_claude(question)
        print(f"[CLAUDE]  ({claude_result['_seconds']}s, valid JSON: {claude_result['_valid_json']})")
        print(f"  reply:     {claude_result.get('reply')}")
        print(f"  resolved:  {claude_result.get('resolved')}")
        print(f"  language:  {claude_result.get('language')}")

        gemini_result = ask_gemini(question)
        print(f"[GEMINI]  ({gemini_result['_seconds']}s, valid JSON: {gemini_result['_valid_json']})")
        print(f"  reply:     {gemini_result.get('reply')}")
        print(f"  resolved:  {gemini_result.get('resolved')}")
        print(f"  language:  {gemini_result.get('language')}")
        print()


if __name__ == "__main__":
    main()