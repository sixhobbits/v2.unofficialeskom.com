""" @bruin
name: raw.integrated_results
connection: eskom_weekly
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

depends:
    - raw.integrated_results_content

description: |
    Parsed integrated-results PDF text. Reads each unique PDF from
    raw.integrated_results_content, runs pdftotext -layout (cached on disk
    next to the PDF), and returns one row per content_hash with the extracted
    text. Pure transform — no HTTP.

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
# pdf_path in *_content is the absolute path on whichever host first downloaded
# the PDF (laptop, het, oc). Resolve against this checkout's warehouse instead.
PDF_DIR = (
    Path(__file__).resolve().parents[3]
    / "warehouse" / "integrated_results" / "pdfs"
)


def materialize() -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute("""
            SELECT content_hash, pdf_url, filename, pdf_path
            FROM raw.integrated_results_content
        """).fetchall()
    finally:
        con.close()

    out = []
    for content_hash, pdf_url, filename, pdf_path in rows:
        if filename and (PDF_DIR / filename).is_file():
            pdf_path = str(PDF_DIR / filename)
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
