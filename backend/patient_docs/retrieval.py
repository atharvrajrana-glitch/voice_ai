"""
Retrieves the most relevant chunks from a patient's own uploaded
documents for a given question. Fails safe: returns an empty list
instead of crashing if the store is empty or errors.
"""

from .vector_store import search_chunks


def retrieve_relevant_chunks(question: str, session_id: str, n_results: int = 3) -> list[dict]:
    try:
        results = search_chunks(question, session_id, n_results=n_results)
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
            }
            for doc, meta in zip(documents, metadatas)
        ]
    except Exception as e:
        print(f"[patient_docs] retrieval failed: {e}")
        return []
