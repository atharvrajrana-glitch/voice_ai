"""Extract embedded PDF text, with local OCR fallback for scanned pages."""

import io
import os
import shutil
from pathlib import Path

from pypdf import PdfReader


class OCRUnavailableError(RuntimeError):
    """Raised when a scanned page needs OCR but its local runtime is absent."""


def _ocr_page(file_bytes: bytes, page_number: int) -> str:
    """Render one PDF page and return text recognized by local Tesseract."""
    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
    except ImportError as error:
        raise OCRUnavailableError(
            "OCR Python packages are not installed. Install backend requirements."
        ) from error

    tesseract_path = shutil.which("tesseract")
    if not tesseract_path:
        standard_windows_path = Path(
            os.environ.get("ProgramFiles", r"C:\\Program Files")
        ) / "Tesseract-OCR" / "tesseract.exe"
        if standard_windows_path.is_file():
            tesseract_path = str(standard_windows_path)

    if not tesseract_path:
        raise OCRUnavailableError(
            "Tesseract OCR is not installed or is not available on PATH."
        )

    pytesseract.pytesseract.tesseract_cmd = tesseract_path

    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as document:
            page = document.load_page(page_number - 1)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            with Image.open(io.BytesIO(pixmap.tobytes("png"))) as image:
                return pytesseract.image_to_string(image).strip()
    except pytesseract.TesseractNotFoundError as error:
        raise OCRUnavailableError(
            "Tesseract OCR is not installed or is not available on PATH."
        ) from error


def extract_pages(file_bytes: bytes) -> list[dict]:
    """Extract every readable page, preferring embedded text over OCR."""
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        extraction_method = "embedded_text"
        if not text:
            text = _ocr_page(file_bytes, i)
            extraction_method = "ocr"
        if text:
            pages.append({"page": i, "text": text, "extraction_method": extraction_method})
    return pages


def chunk_page(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        start = end - overlap
    return [c for c in chunks if c]
