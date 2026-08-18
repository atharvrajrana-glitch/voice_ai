"""
Wraps ChromaDB for hospital document search.

Same logic as your original vector_store.py, with two fixes:
1. The chroma_db path is now built relative to THIS file, not the
   current working directory — so it works no matter where uvicorn
   is launched from.
2. Import is now relative (`.embeddings`), matching this file's new
   location inside backend/rag/.
"""

import asyncio
import os
import chromadb

from .embeddings import create_embedding

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")

client = chromadb.PersistentClient(path=CHROMA_PATH)

collection = client.get_or_create_collection(name="hospital_documents")


def _add_to_collection(chunk, filename, chunk_id, embedding):
    collection.add(
        ids=[chunk_id],
        documents=[chunk],
        embeddings=[embedding],
        metadatas=[{"source": filename}],
    )


async def add_document(chunk, filename, chunk_id):
    embedding = await create_embedding(chunk)
    await asyncio.to_thread(_add_to_collection, chunk, filename, chunk_id, embedding)


def _query_collection(query_embedding, n_results):
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
    )


async def search_documents(query, n_results=3):
    query_embedding = await create_embedding(query)
    return await asyncio.to_thread(_query_collection, query_embedding, n_results)
