"""List and fetch Eskom media statement articles from the news category."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

from .fetch import get


def _classes(attrs: dict[str, str]) -> set[str]:
    return set(attrs.get("class", "").split())


def _clean_text(value: str) -> str:
    return " ".join(unescape(value).split())


def _same_site(url: str) -> bool:
    return urlparse(url).netloc in {"", "www.eskom.co.za", "eskom.co.za"}


@dataclass
class NewsListingItem:
    article_url: str
    title: str | None = None
    published_at: str | None = None
    modified_at: str | None = None


class _NewsListingParser(HTMLParser):
    def __init__(self, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.items: list[NewsListingItem] = []
        self.next_url: str | None = None
        self.max_page: int | None = None
        self._in_news_article = False
        self._article_depth = 0
        self._in_entry_title = False
        self._current: NewsListingItem | None = None
        self._capture_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {name.lower(): value or "" for name, value in attrs_list}
        tag = tag.lower()
        classes = _classes(attrs)

        if tag == "article" and "category-news" in classes:
            self._in_news_article = True
            self._article_depth = 1
            self._current = None
            return

        if self._in_news_article:
            self._article_depth += 1
            if tag == "h2" and "entry-title" in classes:
                self._in_entry_title = True
            elif tag == "a" and self._in_entry_title and self._current is None and "href" in attrs:
                self._current = NewsListingItem(article_url=urljoin(self.page_url, attrs["href"]))
                self._capture_title = True
                self._title_parts = []
            elif tag == "time" and self._current is not None:
                if "published" in classes:
                    self._current.published_at = attrs.get("datetime") or None
                elif "updated" in classes:
                    self._current.modified_at = attrs.get("datetime") or None
            return

        if tag == "a" and "href" in attrs:
            href = urljoin(self.page_url, attrs["href"])
            if "next" in classes and "page-numbers" in classes:
                self.next_url = href
            if "page-numbers" in classes:
                text = attrs.get("aria-label", "")
                page_no = int(text) if text.isdigit() else None
                if page_no is not None:
                    self.max_page = max(self.max_page or page_no, page_no)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._capture_title and tag == "a":
            if self._current is not None:
                self._current.title = _clean_text("".join(self._title_parts)) or None
            self._capture_title = False
            self._title_parts = []
        if self._in_entry_title and tag == "h2":
            self._in_entry_title = False

        if self._in_news_article:
            self._article_depth -= 1
            if self._article_depth <= 0:
                if self._current and _same_site(self._current.article_url):
                    self.items.append(self._current)
                self._in_news_article = False
                self._in_entry_title = False
                self._current = None

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_parts.append(data)


@dataclass
class ArticleContent:
    canonical_url: str | None = None
    title: str | None = None
    published_at: str | None = None
    modified_at: str | None = None
    category: str | None = None
    og_image_url: str | None = None
    text_parts: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    media_urls: list[str] = field(default_factory=list)


class _ArticleParser(HTMLParser):
    def __init__(self, article_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.article_url = article_url
        self.content = ArticleContent()
        self._in_entry_content = False
        self._entry_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {name.lower(): value or "" for name, value in attrs_list}
        tag = tag.lower()
        classes = _classes(attrs)

        if tag == "link" and attrs.get("rel") == "canonical":
            self.content.canonical_url = attrs.get("href") or None
        elif tag == "meta":
            prop = attrs.get("property")
            if prop == "article:published_time":
                self.content.published_at = attrs.get("content") or None
            elif prop == "article:modified_time":
                self.content.modified_at = attrs.get("content") or None
            elif prop == "article:section":
                self.content.category = attrs.get("content") or None
            elif prop in {"og:image", "og:image:secure_url"} and not self.content.og_image_url:
                self.content.og_image_url = attrs.get("content") or None

        if tag in {"script", "style", "nav", "aside"}:
            self._skip_depth += 1

        if tag == "h1" and "entry-title" in classes:
            self._in_title = True
            self._title_parts = []

        if tag == "div" and "entry-content" in classes:
            self._in_entry_content = True
            self._entry_depth = 1
            return

        if self._in_entry_content:
            self._entry_depth += 1
            if tag == "a" and attrs.get("href"):
                self.content.links.append(urljoin(self.article_url, attrs["href"]))
            elif tag in {"img", "source"}:
                for attr_name in ("src", "data-src"):
                    if attrs.get(attr_name):
                        self.content.media_urls.append(urljoin(self.article_url, attrs[attr_name]))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._in_title and tag == "h1":
            self.content.title = _clean_text("".join(self._title_parts)) or None
            self._in_title = False
            self._title_parts = []

        if self._skip_depth and tag in {"script", "style", "nav", "aside"}:
            self._skip_depth -= 1

        if self._in_entry_content:
            self._entry_depth -= 1
            if tag in {"p", "li", "h2", "h3", "h4", "tr", "blockquote", "div"}:
                self.content.text_parts.append("\n")
            if self._entry_depth <= 0:
                self._in_entry_content = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._in_entry_content and not self._skip_depth:
            cleaned = _clean_text(data)
            if cleaned:
                self.content.text_parts.append(cleaned)


def list_news_page(page_url: str) -> tuple[list[NewsListingItem], str | None, int]:
    """Return listing items, next-page URL, and HTTP status for a news page."""
    body, final_url, status = get(page_url, headers={"Accept": "text/html"})
    if status != 200:
        return [], None, status
    parser = _NewsListingParser(final_url)
    parser.feed(body.decode("utf-8", errors="replace"))
    return parser.items, parser.next_url, status


def fetch_article(article_url: str) -> dict[str, Any]:
    """Fetch and parse one media statement article."""
    body, final_url, status = get(article_url, headers={"Accept": "text/html"})
    if status != 200 or not body:
        return {
            "article_url": article_url,
            "canonical_url": None,
            "title": None,
            "published_at": None,
            "modified_at": None,
            "category": None,
            "og_image_url": None,
            "text_content": None,
            "text_length": None,
            "links_json": "[]",
            "media_urls_json": "[]",
            "content_hash": None,
            "byte_size": len(body) if body else None,
            "http_status": status,
            "error": f"http {status}",
        }

    html = body.decode("utf-8", errors="replace")
    parser = _ArticleParser(final_url)
    parser.feed(html)
    content = parser.content
    text = _clean_text("\n".join(content.text_parts))
    links = sorted(set(content.links))
    media_urls = sorted(set(content.media_urls))
    canonical_url = content.canonical_url or final_url
    digest_source = "\n".join([canonical_url, content.title or "", text])

    return {
        "article_url": article_url,
        "canonical_url": canonical_url,
        "title": content.title,
        "published_at": content.published_at,
        "modified_at": content.modified_at,
        "category": content.category,
        "og_image_url": content.og_image_url,
        "text_content": text,
        "text_length": len(text),
        "links_json": json.dumps(links, ensure_ascii=True),
        "media_urls_json": json.dumps(media_urls, ensure_ascii=True),
        "content_hash": hashlib.sha256(digest_source.encode("utf-8")).hexdigest(),
        "byte_size": len(body),
        "http_status": status,
        "error": None,
    }


def fetch_news(
    start_url: str,
    max_pages: int | None = None,
    known_urls: set[str] | None = None,
) -> Iterable[dict[str, Any]]:
    """Yield one parsed article dict per article advertised in the news category.

    known_urls: URLs already in the content store. Pagination stops as soon as
    a full listing page contains only known URLs — avoids re-crawling history.
    """
    seen_pages: set[str] = set()
    seen_articles: set[str] = set()
    next_url: str | None = start_url
    pages_seen = 0

    while next_url:
        if next_url in seen_pages:
            break
        seen_pages.add(next_url)
        pages_seen += 1
        print(f"Fetching news page {pages_seen}: {next_url}", flush=True)

        items, following_url, list_status = list_news_page(next_url)
        if list_status != 200:
            yield {
                "article_url": None,
                "canonical_url": None,
                "title": None,
                "published_at": None,
                "modified_at": None,
                "category": None,
                "og_image_url": None,
                "text_content": None,
                "text_length": None,
                "links_json": "[]",
                "media_urls_json": "[]",
                "content_hash": None,
                "byte_size": None,
                "http_status": list_status,
                "error": f"list page http {list_status}: {next_url}",
            }
            return

        for item in items:
            if item.article_url in seen_articles:
                continue
            seen_articles.add(item.article_url)
            if len(seen_articles) % 50 == 0:
                print(f"Fetched {len(seen_articles)} news articles...", flush=True)
            try:
                rec = fetch_article(item.article_url)
                rec["title"] = rec["title"] or item.title
                rec["published_at"] = rec["published_at"] or item.published_at
                rec["modified_at"] = rec["modified_at"] or item.modified_at
                yield rec
            except Exception as exc:
                yield {
                    "article_url": item.article_url,
                    "canonical_url": None,
                    "title": item.title,
                    "published_at": item.published_at,
                    "modified_at": item.modified_at,
                    "category": None,
                    "og_image_url": None,
                    "text_content": None,
                    "text_length": None,
                    "links_json": "[]",
                    "media_urls_json": "[]",
                    "content_hash": None,
                    "byte_size": None,
                    "http_status": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }

        if max_pages is not None and pages_seen >= max_pages:
            break
        # Stop paginating if every article on this page was already known.
        if known_urls and all(item.article_url in known_urls for item in items):
            print(f"All articles on page {pages_seen} already known — stopping.", flush=True)
            break
        next_url = following_url
