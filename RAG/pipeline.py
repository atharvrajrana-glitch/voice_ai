import asyncio

from .vector_store import search_documents
from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)


def _generate_content(prompt: str):
    return client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0,
    )


async def generate_answer(question: str):

    # Retrieve relevant hospital information
    results = await search_documents(
        question,
        n_results=3
    )

    documents = results["documents"][0]
    metadata = results["metadatas"][0]

    # Combine retrieved documents
    context = "\n\n".join(documents)

    prompt = f"""
You are the AI voice assistant for MedClear General Hospital.

Use ONLY the hospital information provided below to answer.

IMPORTANT RULES:

1. Do not invent hospital information.
2. If the answer is not present in the context, say:
   "I don't have that information in the hospital system."
3. Answer in the same language/style as the patient.
4. If the patient speaks English, answer in English.
5. If the patient speaks Hindi, answer in Hindi.
6. If the patient speaks Hinglish, answer naturally in Hinglish.
7. Keep answers short and suitable for a voice assistant.
8. Do not diagnose medical conditions.
9. Do not prescribe medicines.
10. For emergency situations, follow the hospital emergency policy.

Hospital Context:
----------------
{context}
----------------

Patient Question:
{question}
"""

    response = await asyncio.to_thread(_generate_content, prompt)

    return {
        "reply": response.choices[0].message.content.strip(),
        "sources": [
            item["source"]
            for item in metadata
        ],
        "resolved": True
    }
