from loader import load_documents
from chunker import chunk_text


documents = load_documents()

print("Documents loaded:", len(documents))

for document in documents:
    chunks = chunk_text(document["text"])

    print("\n-------------------------")
    print("File:", document["filename"])
    print("Chunks:", len(chunks))

    for i, chunk in enumerate(chunks[:2]):
        print(f"\nChunk {i}:")
        print(chunk)