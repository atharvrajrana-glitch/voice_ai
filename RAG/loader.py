from pathlib import Path
import os

# Try multiple paths to find the Docs folder
# 1. /app/Docs (Docker volume mount)
# 2. /app/RAG/../Docs (relative from RAG mount)
# 3. ./Docs (relative from app root)

possible_paths = [
    Path("/app/Docs"),
    Path("/app") / ".." / "Docs",
    Path("./Docs"),
    Path("../Docs"),
    Path("/workspace/Docs"),  # For development
]

DOCUMENTS_DIR = None
for path in possible_paths:
    if path.exists():
        DOCUMENTS_DIR = path.resolve()
        break

if DOCUMENTS_DIR is None:
    DOCUMENTS_DIR = Path("/app/Docs")  # Default fallback

print(f"[RAG Loader] DOCUMENTS_DIR = {DOCUMENTS_DIR}")
print(f"[RAG Loader] DOCUMENTS_DIR exists = {DOCUMENTS_DIR.exists()}")

def load_documents():
    documents = []
    
    if not DOCUMENTS_DIR.exists():
        print(f"[ERROR] Documents directory not found: {DOCUMENTS_DIR}")
        return documents

    for file_path in sorted(DOCUMENTS_DIR.glob("*.txt")):
        try:
            text = file_path.read_text(encoding="utf-8")
            documents.append({
                "filename": file_path.name,
                "text": text
            })
            print(f"[RAG Loader] ✓ Loaded: {file_path.name}")
        except Exception as e:
            print(f"[ERROR] Failed to load {file_path.name}: {e}")

    print(f"[RAG Loader] Total documents loaded: {len(documents)}")
    return documents    