"""
Retrieves the most relevant chunks from a patient's own uploaded
documents for a given question. Fails safe: returns an empty list
instead of crashing if the store is empty or errors.
"""

import re
from .vector_store import search_chunks


def _normalize_query(question: str) -> str:
    """
    Normalize query text to improve embedding consistency between
    voice (from Speech Recognition API) and typed input.
    
    - Removes extra whitespace
    - Strips punctuation for core matching
    - Converts to lowercase for consistency
    """
    # Remove leading/trailing whitespace
    text = question.strip()
    
    # Remove multiple consecutive spaces and normalize
    text = re.sub(r'\s+', ' ', text)
    
    # Remove trailing punctuation that might vary between voice/text
    # (but keep it for the actual query to Groq)
    text = re.sub(r'[.!?,;:]+$', '', text).strip()
    
    return text


async def retrieve_relevant_chunks(question: str, session_id: str, n_results: int = 3) -> list[dict]:
    try:
        # Normalize the question to improve consistency between voice and text input
        normalized_question = _normalize_query(question)
        print(f"[patient_docs] normalized query: original='{question}' normalized='{normalized_question}'")
        
        # Try with normalized question first
        results = await search_chunks(normalized_question, session_id, n_results=n_results)
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        
        # If no results with normalized query, try with original (fallback)
                # If no results with normalized query, try with original (fallback)
        if not documents:
            print(f"[patient_docs] no results with normalized query, trying original")
            results = await search_chunks(question, session_id, n_results=n_results)
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]

        return [
            {
                "text": doc,
                "document": meta.get("document"),
                "page": meta.get("page"),
                "test_name": meta.get("test_name"),
                "document_type": meta.get("document_type"),
                "status": meta.get("status"),
                "chunk_type": meta.get("chunk_type"),
                "headers": meta.get("headers"),
                "column_types": meta.get("column_types"),
                "table_number": meta.get("table_number"),
            }
            for doc, meta in zip(documents, metadatas)
        ]

    except Exception as e:
        print(f"[patient_docs] retrieval failed: {e}")
        return []

