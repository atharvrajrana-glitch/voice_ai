"""
Retrieval helper used by the AI core.

Deliberately fails SAFE: if the vector store is empty, missing, or
errors for any reason, this returns None instead of crashing the whole
conversation — the AI core then just answers without hospital-specific
grounding, same as it did before RAG existed.
"""

from .vector_store import search_documents


def retrieve_hospital_context(question: str, n_results: int = 3):
    try:
        results = search_documents(question, n_results=n_results)
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        if not documents:
            return None, []

        context_text = "\n\n".join(documents)
        sources = [m.get("source", "unknown") for m in metadatas]
        return context_text, sources

    except Exception as e:
        print(f"[rag] retrieval failed, continuing without hospital context: {e}")
        return None, []