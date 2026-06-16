#!/usr/bin/env python3
"""
Scrape monthly Eskom analysis threads from Bluesky and emit Docusaurus blog posts.
"""
import json
import os
import re
import time
import urllib.request
from pathlib import Path

ACTOR = "sixhobbits.bsky.social"
BLOG_DIR = Path(__file__).parent / "beta.unofficialeskom.com" / "blog"
API = "https://public.api.bsky.app/xrpc"

# Slugs to never create (e.g. duplicates superseded by a better hand-written post)
SKIP_SLUGS = {
    "2026-05-05-eskom-data-april-2026",
}

# Keywords that identify a monthly analysis root post
MONTHLY_KEYWORDS = re.compile(
    r"eskom\s+data\s*[-–]?\s*(january|february|march|april|may|june|july|august|september|october|november|december|\w+\s+\d{4})|"
    r"eskom\s+(data|stats?)\s*[-–]?\s*\w+\s+\d{4}|"
    r"^eskom\s+\w+\s+data\b",
    re.IGNORECASE,
)


def fetch(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get_all_posts(actor):
    """Paginate through the full author feed, return all posts."""
    posts = []
    cursor = None
    while True:
        url = f"{API}/app.bsky.feed.getAuthorFeed?actor={actor}&limit=100"
        if cursor:
            url += f"&cursor={urllib.parse.quote(cursor)}"
        data = fetch(url)
        batch = data.get("feed", [])
        if not batch:
            break
        posts.extend(batch)
        cursor = data.get("cursor")
        if not cursor:
            break
        time.sleep(0.3)
    return posts


def get_thread(uri):
    """Fetch the full thread for a post URI."""
    url = f"{API}/app.bsky.feed.getPostThread?uri={urllib.parse.quote(uri)}&depth=100"
    data = fetch(url)
    return data.get("thread", {})


def collect_replies(thread_node, root_uri, results=None):
    """DFS collect all replies in thread order."""
    if results is None:
        results = []
    post = thread_node.get("post", {})
    if post:
        results.append(post)
    for reply in thread_node.get("replies", []):
        # Only follow replies by the same author
        reply_post = reply.get("post", {})
        if reply_post.get("author", {}).get("handle") == ACTOR:
            collect_replies(reply, root_uri, results)
    return results


def facets_to_markdown(text, facets):
    """Convert AT Protocol facets to markdown links."""
    if not facets:
        return text
    # Build list of (byteStart, byteEnd, replacement)
    encoded = text.encode("utf-8")
    replacements = []
    for facet in facets:
        index = facet.get("index", {})
        byte_start = index.get("byteStart", 0)
        byte_end = index.get("byteEnd", 0)
        original_bytes = encoded[byte_start:byte_end]
        original = original_bytes.decode("utf-8")
        for feature in facet.get("features", []):
            ftype = feature.get("$type", "")
            if ftype == "app.bsky.richtext.facet#link":
                uri = feature.get("uri", "")
                replacements.append((byte_start, byte_end, f"[{original}]({uri})"))
            elif ftype == "app.bsky.richtext.facet#mention":
                did = feature.get("did", "")
                replacements.append((byte_start, byte_end, f"**{original}**"))
    # Apply replacements in reverse order (so byte offsets stay valid)
    replacements.sort(key=lambda x: x[0], reverse=True)
    result = bytearray(encoded)
    for start, end, replacement in replacements:
        result[start:end] = replacement.encode("utf-8")
    return result.decode("utf-8")


def thread_to_markdown(posts):
    """Join thread posts into a single markdown body."""
    parts = []
    first = True
    for post in posts:
        rec = post.get("record", {})
        text = rec.get("text", "").strip()
        facets = rec.get("facets", [])
        text = facets_to_markdown(text, facets)
        if text:
            parts.append(text)
        # Prefer the embed view (has CDN URLs); fall back to record embed placeholder
        embed_view = post.get("embed", {})
        if embed_view.get("$type") == "app.bsky.embed.images#view":
            for img in embed_view.get("images", []):
                alt = img.get("alt", "")
                url = img.get("fullsize", img.get("thumb", ""))
                if url:
                    parts.append(f"![{alt or 'chart'}]({url})")
        elif rec.get("embed", {}).get("$type") == "app.bsky.embed.images":
            for img in rec["embed"].get("images", []):
                alt = img.get("alt", "")
                parts.append(f"*[Image: {alt or 'chart'}]*")
        # Insert truncate marker after first post
        if first and text:
            parts.append("{/* truncate */}")
            first = False
    return "\n\n".join(parts)


def slug_from_title(title, date_str):
    """Generate a blog post slug."""
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    slug = slug[:60].rstrip("-")
    return f"{date_str}-{slug}"


def infer_title(text, date_str):
    """Try to extract a clean title from the first post text."""
    first_line = text.split("\n")[0].strip()
    # Capitalise "eskom data - month year" style
    if re.match(r"eskom\s+data", first_line, re.IGNORECASE):
        return first_line.title().replace("Eskom Data", "Eskom Data")
    if len(first_line) < 80:
        return first_line
    return f"Eskom data — {date_str}"


def is_monthly_analysis(text):
    return bool(MONTHLY_KEYWORDS.search(text[:200]))


def already_exists(slug):
    return (BLOG_DIR / slug).exists()


def write_post(slug, title, date_str, body):
    post_dir = BLOG_DIR / slug
    post_dir.mkdir(parents=True, exist_ok=True)
    md_path = post_dir / "index.md"
    content = f"""---
slug: {slug.split("-", 3)[-1]}
title: "{title.replace('"', "'")}"
authors: [gareth]
date: {date_str}
---

{body}
"""
    md_path.write_text(content)
    print(f"  wrote {md_path}")


def main():
    import urllib.parse  # noqa — needed in get_all_posts

    print(f"Fetching all posts for {ACTOR}...")
    all_posts = get_all_posts(ACTOR)
    print(f"  {len(all_posts)} feed items fetched")

    # Find root posts that look like monthly analysis
    roots = []
    for item in all_posts:
        post = item["post"]
        rec = post["record"]
        reply = rec.get("reply")
        if reply:
            continue
        text = rec.get("text", "")
        if is_monthly_analysis(text):
            roots.append(post)

    print(f"  {len(roots)} monthly analysis threads identified")

    for root in roots:
        rec = root["record"]
        date_str = rec["createdAt"][:10]
        first_text = rec.get("text", "").strip()
        title = infer_title(first_text, date_str)
        slug = slug_from_title(title, date_str)

        if slug in SKIP_SLUGS:
            print(f"  skip (excluded): {slug}")
            continue
        if already_exists(slug):
            print(f"  skip (exists): {slug}")
            continue

        print(f"  fetching thread: {title} ({date_str})")
        try:
            thread = get_thread(root["uri"])
            posts = collect_replies(thread, root["uri"])
            body = thread_to_markdown(posts)
            write_post(slug, title, date_str, body)
            time.sleep(0.5)
        except Exception as e:
            print(f"  ERROR on {root['uri']}: {e}")

    print("Done.")


if __name__ == "__main__":
    import urllib.parse
    main()
