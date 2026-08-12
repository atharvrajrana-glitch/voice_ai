from loader import load_documents
from chunker import chunk_text
from vector_store import add_document


def ingest_documents():

    documents = load_documents()

    total_chunks = 0

    for document in documents:

        filename = document["filename"]
        text = document["text"]

        chunks = chunk_text(
            text,
            chunk_size=400,
            overlap=50
        )

        for index, chunk in enumerate(chunks):

            chunk_id = f"{filename}_{index}"

            add_document(
                chunk=chunk,
                filename=filename,
                chunk_id=chunk_id
            )

            total_chunks += 1

            print(
                f"Added: {filename} → chunk {index}"
            )

    print(
        f"\nFinished! Added {total_chunks} chunks."
    )


if __name__ == "__main__":
    ingest_documents()