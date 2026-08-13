"""Deterministic extraction of searchable lab-result rows from report text."""

import re


_NUMBER = r"\d+(?:[.,]\d+)?"
_RANGE = rf"(?P<low>{_NUMBER})\s*(?:-|–|to)\s*(?P<high>{_NUMBER})"
_LAB_ROW = re.compile(
    rf"^\s*(?P<test>[A-Za-z][A-Za-z0-9 ()/%+.-]{{1,80}}?)\s+"
    rf"(?P<result>{_NUMBER})\s+{_RANGE}"
    rf"(?:\s+(?P<unit>[A-Za-zµμ/%^0-9.-]+))?\s*$",
    re.IGNORECASE,
)


def detect_document_type(text: str) -> str:
    normalized = text.upper()
    if "COMPLETE BLOOD COUNT" in normalized or re.search(r"\bCBC\b", normalized):
        return "CBC"
    if "LAB" in normalized or "REFERENCE RANGE" in normalized:
        return "laboratory_report"
    return "document"


def _to_number(value: str) -> float:
    return float(value.replace(",", "."))


def extract_lab_rows(text: str, page: int, document_type: str) -> list[dict]:
    """Extract rows containing test, result, reference range and optional unit.

    Rows are only accepted when both numeric range endpoints are present. This
    avoids guessing medical meaning from incomplete OCR output.
    """
    rows = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        match = _LAB_ROW.match(line)
        if not match:
            continue

        result = _to_number(match.group("result"))
        low = _to_number(match.group("low"))
        high = _to_number(match.group("high"))
        if low > high:
            continue

        status = "low" if result < low else "high" if result > high else "normal"
        test_name = match.group("test").strip(" .:-")
        unit = (match.group("unit") or "").strip()
        reference_range = f"{match.group('low')}-{match.group('high')}"
        evidence = f"{test_name}: {match.group('result')} {unit} (reference {reference_range})".strip()
        rows.append(
            {
                "test_name": test_name,
                "result": result,
                "result_display": match.group("result"),
                "unit": unit,
                "reference_range": reference_range,
                "status": status,
                "page": page,
                "document_type": document_type,
                "evidence": evidence,
            }
        )
    return rows


def lab_row_chunk(row: dict) -> str:
    """A self-contained chunk ensures a table row is never split during RAG."""
    unit = f" {row['unit']}" if row["unit"] else ""
    return (
        f"Medical test: {row['test_name']}\n"
        f"Result: {row['result_display']}{unit}\n"
        f"Reference range: {row['reference_range']}\n"
        f"Status based on this report's reference range: {row['status']}\n"
        f"Document type: {row['document_type']}\n"
        f"Evidence: {row['evidence']}"
    )
