"""Unit tests for the hand-written scraper library (eskom_portal).

Pins scrape_csv's branch behaviour and the pure CSV-parsing helpers. The HTTP
layer (get / get_meta) is monkeypatched so these are deterministic + offline.
"""
from __future__ import annotations

import eskom_portal.csv_scrape as cs


def _patch_http(monkeypatch, *, page=(b"", 200), csv=(b"", 200, {})):
    """page -> (body, status); csv -> (body, status, headers)."""
    page_body, page_status = page
    csv_body, csv_status, csv_hdrs = csv
    monkeypatch.setattr(cs, "get", lambda url, headers=None: (page_body, url, page_status))
    monkeypatch.setattr(
        cs, "get_meta",
        lambda url, headers=None: (csv_body, url, csv_status, csv_hdrs),
    )


PAGE_WITH_LINK = b'<html><body><a href="https://x/data/file.csv">Download CSV</a></body></html>'
GOOD_CSV = b"Date Time Hour Beginning,Residual Demand\n2026-06-01 00:00:00,20000\n2026-06-01 01:00:00,19000\n"


def test_scrape_csv_happy_path(monkeypatch):
    _patch_http(
        monkeypatch,
        page=(PAGE_WITH_LINK, 200),
        csv=(GOOD_CSV, 200, {"etag": '"abc"', "last-modified": "Mon, 02 Jun 2026 04:09:00 GMT", "content-length": "84"}),
    )
    r = cs.scrape_csv("https://eskom/dataportal/demand-side/x/")
    assert r["http_status"] == 200
    assert r["error"] is None
    assert r["csv_url"] == "https://x/data/file.csv"
    assert r["etag"] == '"abc"'
    assert r["last_modified"].startswith("Mon, 02 Jun")
    assert r["content_text"].startswith("Date Time Hour Beginning")
    assert len(r["rows"]) == 2  # both data rows parsed


def test_scrape_csv_page_404(monkeypatch):
    _patch_http(monkeypatch, page=(b"<html>not found</html>", 404))
    r = cs.scrape_csv("https://eskom/dataportal/x/")
    assert r["http_status"] == 404
    assert r["error"] == "page fetch HTTP 404"
    assert r["csv_url"] is None
    assert r["content_text"] == "<html>not found</html>"  # body preserved for replay


def test_scrape_csv_no_link(monkeypatch):
    _patch_http(monkeypatch, page=(b"<html><body>no downloads here</body></html>", 200))
    r = cs.scrape_csv("https://eskom/dataportal/x/")
    assert r["error"] == "no CSV link on graph page"
    assert r["csv_url"] is None
    assert r["rows"] == []


def test_scrape_csv_link_returns_html(monkeypatch):
    _patch_http(
        monkeypatch,
        page=(PAGE_WITH_LINK, 200),
        csv=(b"<!DOCTYPE html><html>error page</html>", 200, {}),
    )
    r = cs.scrape_csv("https://eskom/dataportal/x/")
    assert r["error"] == "CSV link returned HTML"
    assert r["rows"] == []


def test_scrape_csv_csv_http_error(monkeypatch):
    _patch_http(monkeypatch, page=(PAGE_WITH_LINK, 200), csv=(b"", 503, {}))
    r = cs.scrape_csv("https://eskom/dataportal/x/")
    assert r["http_status"] == 503
    assert r["error"] == "CSV HTTP 503"


# ---- pure helpers ----

def test_parse_csv_text_basic():
    rows = cs.parse_csv_text(GOOD_CSV.decode())
    assert len(rows) == 2
    assert rows[0]["value"] == 20000.0
    assert rows[0]["timestamp"] is not None


def test_sniff_delimiter_semicolon():
    assert cs._sniff_delimiter("a;b;c\n1;2;3") == ";"


def test_parse_number_handles_thousands_and_blank():
    # comma delimiter implies '.' decimals; verify blank -> None and numeric parse
    assert cs._parse_number("", ",") is None
    assert cs._parse_number("1234.5", ",") == 1234.5


def test_month_candidates_year_rollover():
    import datetime
    assert cs._month_candidates('https://x/wp-content/uploads/2025/11/file.csv?q=1', datetime.date(2026, 1, 9)) == [
        'https://x/wp-content/uploads/2026/01/file.csv?q=1',
        'https://x/wp-content/uploads/2025/12/file.csv?q=1',
    ]


def test_month_recovery_checks_data_and_preserves_metadata(monkeypatch):
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc).date()
    old_month = (today.replace(day=1) - datetime.timedelta(days=40)).replace(day=1)
    old = f'https://x/wp-content/uploads/{old_month:%Y/%m}/file.csv'
    candidate = cs._month_candidates(old, today)[0]
    page = f'<a href="{old}">CSV</a>'.encode()
    monkeypatch.setattr(cs, 'get', lambda url: (page, url, 200))
    calls = []
    def get_meta(url):
        calls.append(url)
        day = old_month if url == old else today
        body = f'Date,Hourly UCLF+OCLF\n{day},1234\n'.encode()
        return body, url, 200, {'etag': url, 'last-modified': 'fresh even for old data'}
    monkeypatch.setattr(cs, 'get_meta', get_meta)
    result = cs.scrape_csv('https://x/graph')
    assert calls == [old, candidate]
    assert result['csv_url'] == candidate
    assert result['etag'] == candidate
    assert str(today) in result['content_text']


def test_bad_month_candidates_keep_linked_csv(monkeypatch):
    old = 'https://x/wp-content/uploads/2020/01/file.csv'
    monkeypatch.setattr(cs, 'get', lambda url: (f'<a href="{old}">CSV</a>'.encode(), url, 200))
    for body, status in [(b'<html>oops</html>', 200), (b'', 404),
                         (b'Date,Residual Demand\n2019-01-01,100\n', 200),
                         (b'Date,Wrong metric\n2099-01-01,100\n', 200)]:
        monkeypatch.setattr(cs, 'get_meta', lambda url, body=body, status=status:
                            (GOOD_CSV, url, 200, {'etag': 'original'}) if url == old else (body, url, status, {}))
        result = cs.scrape_csv('https://x/graph')
        assert result['csv_url'] == old
        assert result['etag'] == 'original'
        assert result['content_text'] == GOOD_CSV.decode()


def test_fresh_link_does_not_probe_month_paths(monkeypatch):
    import datetime
    old = 'https://x/wp-content/uploads/2020/01/file.csv'
    today = datetime.datetime.now(datetime.timezone.utc).date()
    monkeypatch.setattr(cs, 'get', lambda url: (f'<a href="{old}">CSV</a>'.encode(), url, 200))
    calls = []
    def get_meta(url):
        calls.append(url)
        return f'Date,Value\n{today},1\n'.encode(), url, 200, {}
    monkeypatch.setattr(cs, 'get_meta', get_meta)
    cs.scrape_csv('https://x/graph')
    assert calls == [old]


def test_month_probe_timeout_keeps_linked_csv(monkeypatch):
    old = 'https://x/wp-content/uploads/2020/01/file.csv'
    monkeypatch.setattr(cs, 'get', lambda url: (f'<a href="{old}">CSV</a>'.encode(), url, 200))
    def get_meta(url):
        if url != old:
            raise TimeoutError('probe timed out')
        return GOOD_CSV, url, 200, {}
    monkeypatch.setattr(cs, 'get_meta', get_meta)
    assert cs.scrape_csv('https://x/graph')['content_text'] == GOOD_CSV.decode()


# ---------- pages that link several CSV files ----------

RE_PAGE = b"".join(
    f'<a href="https://x/wp-content/uploads/2026/07/{f}">CSV</a>'.encode()
    for f in ("RE_Current_Installed_Capacity.csv", "RE_Maximum_Contribution.csv",
              "RE_Maximum_Peak_Difference.csv", "RE_Annual_Energy_Contribution.csv")
)


def test_csv_file_selects_its_own_link(monkeypatch):
    monkeypatch.setattr(cs, "get", lambda url: (RE_PAGE, url, 200))
    monkeypatch.setattr(cs, "get_meta", lambda url: (b"Name,Value\nWind,1\n", url, 200, {"etag": url}))
    for f in ("RE_Current_Installed_Capacity.csv", "re_maximum_peak_difference.csv",
              "RE_Annual_Energy_Contribution.csv"):
        r = cs.scrape_csv("https://x/renewable-statistics/", f)
        assert r["csv_url"].lower().endswith("/2026/07/" + f.lower())
        assert r["etag"] == r["csv_url"]  # validators belong to that file's response
    assert cs.scrape_csv("https://x/renewable-statistics/")["csv_url"].endswith(
        "RE_Current_Installed_Capacity.csv")  # no csv_file: first link, as before


def test_missing_sibling_link_errors_only_that_file(monkeypatch):
    monkeypatch.setattr(cs, "get", lambda url: (RE_PAGE, url, 200))
    monkeypatch.setattr(cs, "get_meta", lambda url: (b"Name,Value\nWind,1\n", url, 200, {}))
    r = cs.scrape_csv("https://x/renewable-statistics/", "RE_Gone.csv")
    assert r["error"] == "no RE_Gone.csv link on graph page"
    assert r["csv_url"] is None


def test_csv_file_follows_monthly_path_change(monkeypatch):
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc).date()
    old_month = (today.replace(day=1) - datetime.timedelta(days=40)).replace(day=1)
    page = b"".join(f'<a href="https://x/wp-content/uploads/{old_month:%Y/%m}/{f}">CSV</a>'.encode()
                    for f in ("A.csv", "B.csv"))
    monkeypatch.setattr(cs, "get", lambda url: (page, url, 200))

    def get_meta(url):
        day = old_month if f"/{old_month:%Y/%m}/" in url else today
        return f"Date,Value\n{day},1\n".encode(), url, 200, {}
    monkeypatch.setattr(cs, "get_meta", get_meta)
    r = cs.scrape_csv("https://x/graph", "B.csv")
    assert r["csv_url"] == cs._month_candidates(
        f"https://x/wp-content/uploads/{old_month:%Y/%m}/B.csv", today)[0]


def test_csv_datasets_expand_multi_file_pages():
    from eskom_portal.catalog import PORTAL_GRAPHS, csv_datasets
    ds = csv_datasets(PORTAL_GRAPHS)
    slugs = [d["slug"] for d in ds]
    assert len(slugs) == len(set(slugs))  # distinct dataset identities
    re_ds = [d for d in ds if d["page_url"].endswith("/renewable-statistics/")]
    assert [d["csv_file"] for d in re_ds] == [
        "RE_Current_Installed_Capacity.csv", "RE_Annual_Energy_Contribution.csv",
        "RE_Maximum_Contribution.csv", "RE_Maximum_Peak_Difference.csv"]
    assert re_ds[0]["slug"] == "renewables-performance/renewable-statistics"  # history keeps its slug
    assert len(ds) == len(PORTAL_GRAPHS) + 3
