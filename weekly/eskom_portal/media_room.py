"""List and download PDFs from Eskom pages.

The pages are plain HTML with <a href="...pdf"> links. We list them, then
download each (with on-disk cache keyed by URL filename), hash the bytes,
and optionally extract text via pdftotext.
"""
from __future__ import annotations

import hashlib
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urljoin

from .fetch import get

BASE = "https://www.eskom.co.za"


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.hrefs.append(value)
                return


def list_pdf_urls(page_url: str) -> tuple[list[str], int]:
    """Return (sorted unique absolute PDF URLs, http_status)."""
    body, _final, status = get(page_url)
    if status != 200:
        return [], status
    html = body.decode("utf-8", errors="replace")
    parser = _LinkParser()
    parser.feed(html)
    urls = set()
    for href in parser.hrefs:
        if not href.lower().split("?", 1)[0].endswith(".pdf"):
            continue
        urls.add(urljoin(page_url, href))
    return sorted(urls), status


def _safe_filename(url: str) -> str:
    name = unquote(url.rsplit("/", 1)[-1])
    return name.replace("/", "_").replace("\x00", "")


def download_pdf(url: str, dest_dir: Path) -> tuple[Path | None, int, str | None]:
    """Download (if not cached) and return (path, http_status, error)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / _safe_filename(url)
    if path.exists() and path.stat().st_size > 0:
        return path, 200, None
    body, _final, status = get(url)
    if status != 200 or not body:
        return None, status, f"http {status}"
    path.write_bytes(body)
    return path, status, None


def pdf_to_text(pdf_path: Path) -> str:
    """Run pdftotext -layout once per file; cache the .txt alongside."""
    txt_path = pdf_path.with_suffix(".txt")
    if not txt_path.exists():
        subprocess.run(["pdftotext", "-layout", str(pdf_path)], check=True)
    return txt_path.read_text(errors="replace")


def fetch_pdfs(page_url: str, cache_dir: Path) -> Iterable[dict[str, Any]]:
    """Yield one dict per PDF advertised on an Eskom page.

    Each dict: pdf_url, filename, pdf_path, content_hash, byte_size, http_status, error.
    """
    urls, list_status = list_pdf_urls(page_url)
    if list_status != 200:
        yield {
            "pdf_url": page_url,
            "filename": None,
            "pdf_path": None,
            "content_hash": None,
            "byte_size": None,
            "http_status": list_status,
            "error": f"list page http {list_status}",
        }
        return

    for url in urls:
        try:
            path, status, err = download_pdf(url, cache_dir)
            if err or path is None:
                yield {
                    "pdf_url": url,
                    "filename": _safe_filename(url),
                    "pdf_path": None,
                    "content_hash": None,
                    "byte_size": None,
                    "http_status": status,
                    "error": err,
                }
                continue
            body = path.read_bytes()
            yield {
                "pdf_url": url,
                "filename": path.name,
                "pdf_path": str(path),
                "content_hash": hashlib.sha256(body).hexdigest(),
                "byte_size": len(body),
                "http_status": status,
                "error": None,
            }
        except Exception as e:
            yield {
                "pdf_url": url,
                "filename": _safe_filename(url),
                "pdf_path": None,
                "content_hash": None,
                "byte_size": None,
                "http_status": None,
                "error": f"{type(e).__name__}: {e}",
            }


def fetch_presentations(page_url: str, cache_dir: Path) -> Iterable[dict[str, Any]]:
    """Yield one dict per PDF advertised on the presentations page."""
    yield from fetch_pdfs(page_url, cache_dir)
