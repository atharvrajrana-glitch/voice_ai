from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = BASE_DIR / "Docs"



def load_documents():
    documents = []

    for file_path in DOCUMENTS_DIR.glob("*.txt"):
        text = file_path.read_text(encoding="utf-8")

        documents.append({
            "filename": file_path.name,
            "text": text
        })

    return documents    