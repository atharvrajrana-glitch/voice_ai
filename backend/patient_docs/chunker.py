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
        import fitz  
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

def _extract_tables(file_bytes: bytes, page_number: int) -> dict:
    """Detect and extract tables on a page with structure metadata."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return {"text": "", "tables_data": []}

    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as document:
            page = document.load_page(page_number - 1)
            tables = page.find_tables()
            if not tables.tables:
                return {"text": "", "tables_data": []}

            formatted_tables = []
            tables_data = []

            for table_index, table in enumerate(tables.tables, start=1):
                rows = table.extract()
                if not rows:
                    continue

                # First row is header
                headers = [str(h).strip() if h else "" for h in rows[0]]
                headers = [h for h in headers if h]  # Remove empty headers

                # Detect column types
                column_types = []
                for header in headers:
                    header_lower = header.lower()
                    if any(x in header_lower for x in ["code", "id", "serial"]):
                        column_types.append("code")
                    elif any(x in header_lower for x in ["amount", "total", "price", "cost", "charge"]):
                        column_types.append("amount")
                    elif any(x in header_lower for x in ["date", "time", "qty", "unit", "rate"]):
                        column_types.append("metadata")
                    else:
                        column_types.append("description")

                # Extract data rows
                                # Extract data rows, labeling each cell with its column header
                data_rows = []
                lines = [f"[Table {table_index}]"]
                for row in rows[1:]:
                    clean_cells = [str(cell).strip() if cell else "" for cell in row]
                    if not any(clean_cells):
                        continue
                    data_rows.append(clean_cells)
                    labeled_row = "; ".join(
                        f"{headers[idx]}: {clean_cells[idx]}"
                        for idx in range(min(len(headers), len(clean_cells)))
                        if clean_cells[idx]
                    )
                    if labeled_row:
                        lines.append(labeled_row)

                if len(lines) > 1:
                    formatted_tables.append("\n".join(lines))

                    # Store structured table data
                    tables_data.append({
                        "table_number": table_index,
                        "headers": headers,
                        "column_types": column_types,
                        "rows": data_rows,
                        "num_columns": len(headers)
                    })

            return {
                "text": "\n\n".join(formatted_tables),
                "tables_data": tables_data
            }
    except Exception:
        return {"text": "", "tables_data": []}


def extract_pages(file_bytes: bytes) -> list[dict]:
    """Extract every readable page, preferring embedded text over OCR, with table-aware extraction."""
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        extraction_method = "embedded_text"
        if not text:
            text = _ocr_page(file_bytes, i)
            extraction_method = "ocr"

        table_result = _extract_tables(file_bytes, i)
        tables_data = table_result.get("tables_data", [])

        if tables_data:
            extraction_method += "+table"

        if text or tables_data:
            page_data = {
                "page": i,
                "text": text,  # kept separate from table content to avoid duplicate/ambiguous chunks
                "extraction_method": extraction_method,
                "tables": tables_data
            }
            pages.append(page_data)
    return pages


def chunk_page(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        start = end - overlap
    return [c for c in chunks if c]
