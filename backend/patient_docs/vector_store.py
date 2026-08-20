"""
Vector store for PATIENT-UPLOADED documents only.

Deliberately a completely separate ChromaDB collection from the
hospital RAG (backend/../RAG/) — per the requirement that hospital
knowledge and a patient's private documents must never mix.

Isolation between patients: every chunk is tagged with a session_id,
and every query filters by that same session_id. A patient can only
ever retrieve chunks from documents uploaded under their own session.

Reuses the same embedding function as the hospital RAG (imported from
the RAG package) so there's only one embedding implementation to
maintain, not two.
"""

import asyncio
import os
import chromadb
from RAG.embeddings import create_embedding

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")

client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = client.get_or_create_collection(name="patient_documents")


def _add_to_collection(
    chunk_text: str,
    session_id: str,
    document_name: str,
    page: int,
    chunk_id: str,
    embedding: list,  # 🛠️ ADDED: Now the function knows what embedding is!
    extra_metadata: dict | None = None,
):
    metadata = {"session_id": session_id, "document": document_name, "page": page}
    if extra_metadata:
        metadata.update({key: value for key, value in extra_metadata.items() if value is not None})
        
    collection.add(
        ids=[chunk_id],
        documents=[chunk_text],
        embeddings=[embedding], 
        metadatas=[metadata],
    )


async def add_chunk(
    chunk_text: str,
    session_id: str,
    document_name: str,
    page: int,
    chunk_id: str,
    extra_metadata: dict | None = None,
):
    embedding = await create_embedding(chunk_text)
    
    await asyncio.to_thread(
        _add_to_collection,
        chunk_text,
        session_id,
        document_name,
        page,
        chunk_id,
        embedding,       
        extra_metadata,  
    )


def _query_collection(query_embedding, session_id: str, n_results: int):
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where={"session_id": session_id},  # the actual isolation boundary
    )


async def search_chunks(query: str, session_id: str, n_results: int = 3):
    query_embedding = await create_embedding(query)
    return await asyncio.to_thread(_query_collection, query_embedding, session_id, n_results)


def delete_session(session_id: str):
    """Optional cleanup — call this if you want to let a patient wipe their uploaded documents."""
    collection.delete(where={"session_id": session_id})
