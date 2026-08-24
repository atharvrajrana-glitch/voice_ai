"""Turns an uploaded PDF into searchable, patient-scoped vector-store chunks."""

import uuid

from .chunker import OCRUnavailableError, chunk_page, extract_pages
from .medical_report import detect_document_type, extract_lab_rows, lab_row_chunk
from .vector_store import add_chunk , delete_session


async def ingest_pdf(file_bytes: bytes, filename: str, session_id: str) -> dict:
    try:
        delete_session(session_id)
    except Exception :
        pass
    try:
        pages = extract_pages(file_bytes)
    except OCRUnavailableError as error:
        return {
            "success": False,
            "chunks_added": 0,
            "message": f"This PDF contains image-only page(s), but local OCR is unavailable: {error}",
        }

    if not pages:
        return {
            "success": False,
            "chunks_added": 0,
            "message": "No readable text was found in this PDF, even after OCR.",
        }
    total_chunks = 0
    total_lab_rows = 0
    total_tables = 0
    for page_info in pages:
        document_type = detect_document_type(page_info["text"])

        for row in extract_lab_rows(page_info["text"], page_info["page"], document_type):
            await add_chunk(
                lab_row_chunk(row),
                session_id,
                filename,
                page_info["page"],
                str(uuid.uuid4()),
                {
                    "chunk_type": "medical_result",
                    "test_name": row["test_name"],
                    "document_type": row["document_type"],
                    "status": row["status"],
                    "reference_range": row["reference_range"],
                },
            )
            total_chunks += 1
            total_lab_rows += 1

        # Process extracted tables with column metadata
                # Process extracted tables with column metadata
        tables = page_info.get("tables", [])
        for table_data in tables:
            headers = table_data["headers"]
            table_chunk = f"Table: {', '.join(headers)}\n"
            for row in table_data["rows"]:
                labeled_row = "; ".join(
                    f"{headers[idx]}: {row[idx]}"
                    for idx in range(min(len(headers), len(row)))
                    if row[idx]
                )
                table_chunk += labeled_row + "\n"

            await add_chunk(
                table_chunk,
                session_id,
                filename,
                page_info["page"],
                str(uuid.uuid4()),
                {
                    "chunk_type": "table_structure",
                    "table_number": table_data["table_number"],
                    "headers": table_data["headers"],
                    "column_types": table_data["column_types"],
                    "document_type": document_type,
                },
            )
            total_chunks += 1
            total_tables += 1

        if not tables:
            for chunk_text in chunk_page(page_info["text"]):
                await add_chunk(
                    chunk_text,
                    session_id,
                    filename,
                    page_info["page"],
                    str(uuid.uuid4()),
                    {"chunk_type": "page_text", "document_type": document_type},
                )
                total_chunks += 1


    ocr_pages = sum(page["extraction_method"] == "ocr" for page in pages)
    ocr_detail = f" OCR was used on {ocr_pages} page(s)." if ocr_pages else ""
    row_detail = f" Extracted {total_lab_rows} structured lab row(s)." if total_lab_rows else ""
    table_detail = f" Found {total_tables} structured table(s)." if total_tables else ""
    return {
        "success": True,
        "chunks_added": total_chunks,
        "message": f"Processed {len(pages)} page(s) into {total_chunks} searchable sections.{ocr_detail}{row_detail}{table_detail}",
    }

