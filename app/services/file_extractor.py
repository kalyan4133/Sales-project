from __future__ import annotations

from io import BytesIO
from typing import Tuple
import os

import pandas as pd

# Optional imports (install if needed)
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    from docx import Document
except Exception:
    Document = None


SUPPORTED = {".txt", ".pdf", ".docx", ".csv", ".xlsx"}


def extract_text_from_upload(filename: str, data: bytes) -> Tuple[str, str]:
    ext = os.path.splitext((filename or "").lower())[1]

    if ext not in SUPPORTED:
        raise ValueError(f"Unsupported file type: {ext}. Supported: {sorted(SUPPORTED)}")

    if ext == ".txt":
        return data.decode("utf-8", errors="ignore").strip(), "txt"

    if ext == ".pdf":
        if PdfReader is None:
            raise ValueError("PDF support missing. Install: pip install pypdf")
        reader = PdfReader(BytesIO(data))
        pages = []
        for p in reader.pages:
            pages.append(p.extract_text() or "")
        return "\n".join(pages).strip(), "pdf"

    if ext == ".docx":
        if Document is None:
            raise ValueError("DOCX support missing. Install: pip install python-docx")
        doc = Document(BytesIO(data))
        parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(parts).strip(), "docx"

    if ext == ".csv":
        df = pd.read_csv(BytesIO(data))
        return dataframe_to_text(df), "csv"

    if ext == ".xlsx":
        xls = pd.ExcelFile(BytesIO(data))
        chunks = []
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            chunks.append(f"--- Sheet: {sheet} ---\n{dataframe_to_text(df)}")
        return "\n\n".join(chunks).strip(), "xlsx"

    return "", "unknown"


def dataframe_to_text(df: pd.DataFrame, max_rows: int = 200) -> str:
    if df is None or df.empty:
        return ""

    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.head(max_rows)

    cols = df.columns.tolist()
    lines = ["COLUMNS: " + " | ".join(cols)]
    for _, row in df.iterrows():
        vals = [str(row.get(c, "")).strip() for c in cols]
        lines.append("ROW: " + " | ".join(vals))
    return "\n".join(lines)
