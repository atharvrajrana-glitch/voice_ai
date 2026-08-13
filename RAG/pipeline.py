from .vector_store import search_documents
from google import genai
from dotenv import load_dotenv
import os

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


def generate_answer(question: str):

    # Retrieve relevant hospital information
    results = search_documents(
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

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt
    )

    return {
        "reply": response.text.strip(),
        "sources": [
            item["source"]
            for item in metadata
        ],
        "resolved": True
    }