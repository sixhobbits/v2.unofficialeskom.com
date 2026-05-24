""" @bruin
name: raw.media_presentations
connection: eskom_weekly
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

depends:
    - raw.media_presentations_content

description: |
    Parsed presentation text. Reads each unique PDF from
    raw.media_presentations_content, runs pdftotext -layout (cached on
    disk next to the PDF), and returns one row per content_hash with the
    extracted text. Pure transform — no HTTP.

columns:
    - name: content_hash
      type: VARCHAR
    - name: pdf_url
      type: VARCHAR
    - name: filename
      type: VARCHAR
    - name: pdf_path
      type: VARCHAR
    - name: text_content
      type: VARCHAR
    - name: text_length
      type: BIGINT
    - name: error
      type: VARCHAR
@bruin """

from pathlib import Path

import duckdb
import pandas as pd

from eskom_portal.media_room import pdf_to_text

DB_PATH = (
    Path(__file__).resolve().parents[3]
    / "warehouse" / "media_presentations" / "index.duckdb"
)
PDF_DIR = (
    Path(__file__).resolve().parents[3]
    / "warehouse" / "media_presentations" / "pdfs"
)


def materialize() -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute("""
            SELECT content_hash, pdf_url, filename, pdf_path
            FROM raw.media_presentations_content
        """).fetchall()
    finally:
        con.close()

    out = []
    for content_hash, pdf_url, filename, pdf_path in rows:
        if pdf_path and not Path(pdf_path).exists() and filename:
            current_path = PDF_DIR / filename
            if current_path.exists():
                pdf_path = str(current_path)
        if not pdf_path:
            out.append({
                "content_hash": content_hash, "pdf_url": pdf_url,
                "filename": filename, "pdf_path": pdf_path,
                "text_content": None, "text_length": None,
                "error": "no pdf_path",
            })
            continue
        try:
            text = pdf_to_text(Path(pdf_path))
            out.append({
                "content_hash": content_hash, "pdf_url": pdf_url,
                "filename": filename, "pdf_path": pdf_path,
                "text_content": text, "text_length": len(text),
                "error": None,
            })
        except Exception as e:
            out.append({
                "content_hash": content_hash, "pdf_url": pdf_url,
                "filename": filename, "pdf_path": pdf_path,
                "text_content": None, "text_length": None,
                "error": f"{type(e).__name__}: {e}",
            })

    return pd.DataFrame(out, columns=[
        "content_hash", "pdf_url", "filename", "pdf_path",
        "text_content", "text_length", "error",
    ])
