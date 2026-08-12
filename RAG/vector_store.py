import chromadb

from embeddings import create_embedding


client = chromadb.PersistentClient(
    path="./chroma_db"
)

collection = client.get_or_create_collection(
    name="hospital_documents"
)


def add_document(chunk, filename, chunk_id):

    embedding = create_embedding(chunk)

    collection.add(
        ids=[chunk_id],
        documents=[chunk],
        embeddings=[embedding],
        metadatas=[
            {
                "source": filename
            }
        ]
    )


def search_documents(query, n_results=3):

    query_embedding = create_embedding(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results
    )

    return results