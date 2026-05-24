"""Scrape one Eskom Data Portal graph page → embedded PowerBI report → points.

The dsr-decoding logic is lifted near-verbatim from v1.2/eskom_portal/powerbi.py;
the surface API is one function returning a result dict suitable for direct
use in a bruin Python asset's materialize().
"""
from __future__ import annotations

import base64
import datetime as dt
import gzip
import html.parser
import json
import re
import urllib.parse
from typing import Any

from eskom_portal.fetch import get, post_json

POWERBI_API_ROOT = "https://wabi-south-africa-north-a-primary-api.analysis.windows.net/public/reports"
PLOTTED_ROLES = ("Category", "Series", "Y", "Y2")


# ---------- iframe discovery ----------

class _IframeExtractor(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.iframes: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "iframe":
            for k, v in attrs:
                if k.lower() == "src" and v:
                    self.iframes.append(v)


def _find_iframes(page_url: str, body: bytes) -> list[str]:
    parser = _IframeExtractor()
    parser.feed(body.decode("utf-8", errors="replace"))
    abs_urls = [urllib.parse.urljoin(page_url, src) for src in parser.iframes]
    matches = [u for u in abs_urls if "app.powerbi.com/view" in u]
    if matches:
        return matches
    text = body.decode("utf-8", errors="replace")
    return [urllib.parse.urljoin(page_url, m)
            for m in re.findall(r"https://app\.powerbi\.com/view\?r=[^\"' <]+", text)]


def _decode_report_id(iframe_src: str) -> str:
    encoded = urllib.parse.parse_qs(urllib.parse.urlparse(iframe_src).query).get("r", [None])[0]
    if not encoded:
        raise ValueError(f"PowerBI iframe missing r parameter: {iframe_src}")
    payload = json.loads(base64.urlsafe_b64decode(
        (encoded + "=" * (-len(encoded) % 4)).encode()).decode("utf-8"))
    return payload["k"]


# ---------- PowerBI public API ----------

def _http_json(url: str, report_id: str, payload: dict | None = None) -> dict:
    headers = {"Accept": "application/json", "X-PowerBI-ResourceKey": report_id}
    if payload is not None:
        raw = post_json(url, payload, headers)
    else:
        raw, _f, _s = get(url, headers)
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


# ---------- visual config / projections / dsr decode (lifted from v1.2) ----------

def _literal(expr: dict) -> str | None:
    v = expr.get("Literal", {}).get("Value")
    return None if v is None else str(v).strip("'")


def _visual_title(single: dict, fallback: str) -> str:
    for group in ("vcObjects", "objects"):
        for entry in single.get(group, {}).get("title", []):
            text = _literal(entry.get("properties", {}).get("text", {}).get("expr", {}))
            if text:
                return text
    return fallback


def _display_name(single: dict, ref: str) -> str:
    props = single.get("columnProperties", {}).get(ref, {})
    if props.get("displayName"):
        return str(props["displayName"])
    m = re.match(r"^(?:Sum|Min|Max|Average|CountNonNull|Count)\((.+)\)$", ref)
    if m:
        return m.group(1).split(".")[-1].strip()
    return ref.split(".")[-1].strip()


def _plotted_refs(single: dict) -> list[str]:
    refs: list[str] = []
    for role in PLOTTED_ROLES:
        for item in single.get("projections", {}).get(role, []):
            r = item.get("queryRef")
            if r and r not in refs:
                refs.append(r)
    return refs


def _role_indices(single: dict, refs: list[str]) -> dict[str, list[int]]:
    out = {role: [] for role in PLOTTED_ROLES}
    for role in PLOTTED_ROLES:
        for item in single.get("projections", {}).get(role, []):
            r = item.get("queryRef")
            if r in refs:
                out[role].append(refs.index(r))
    return out


def _clone_query(prototype: dict, refs: list[str]) -> dict:
    by_name = {it["Name"]: it for it in prototype.get("Select", []) if it.get("Name")}
    missing = [r for r in refs if r not in by_name]
    if missing:
        raise KeyError(f"projection refs missing in prototype: {missing}")
    q = json.loads(json.dumps(prototype))
    q["Select"] = [by_name[r] for r in refs]
    return q


def _query_payload(report_id: str, metadata: dict, visual_id: str, query: dict) -> dict:
    n = len(query["Select"])
    return {
        "version": "1.0.0",
        "queries": [{
            "Query": {"Commands": [{"SemanticQueryDataShapeCommand": {
                "Query": query,
                "Binding": {
                    "Primary": {"Groupings": [{"Projections": list(range(n))}]},
                    "DataReduction": {"DataVolume": 4, "Primary": {"Top": {"Count": 30000}}},
                    "SuppressedJoinPredicates": [],
                    "Version": 1,
                },
                "ExecutionMetricsKind": 1,
            }}]},
            "CacheKey": "", "QueryId": "",
            "ApplicationContext": {
                "DatasetId": metadata["models"][0]["dbName"],
                "Sources": [{"ReportId": report_id, "VisualId": visual_id}],
            },
        }],
        "cancelQueries": [],
        "modelId": metadata["models"][0]["id"],
    }


def _coerce(v: Any) -> Any:
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if s == "":
            return None
        try:
            return float(s)
        except ValueError:
            return v
    return v


def _decode_rows(result: dict, width: int) -> list[list[Any]]:
    """Decode PowerBI's dsr-encoded result into a list of cell rows."""
    dsr = result["results"][0]["result"]["data"]["dsr"]
    out: list[list[Any]] = []
    prev: list[Any] | None = None
    for ds in dsr.get("DS", []):
        for ph in ds.get("PH", []):
            for k, rows in ph.items():
                if not k.startswith("DM"):
                    continue
                for raw in rows:
                    cells = list(raw.get("C", []))
                    if not cells:
                        continue
                    if "R" in raw and prev is not None:
                        mask = int(raw["R"])
                        merged, cur = [], 0
                        for i in range(width):
                            if mask & (1 << i):
                                merged.append(prev[i])
                            else:
                                merged.append(cells[cur] if cur < len(cells) else None)
                                cur += 1
                        cells = merged
                    if len(cells) < width:
                        cells.extend([None] * (width - len(cells)))
                    if "Ø" in raw:
                        nm = int(raw["Ø"])
                        for i in range(len(cells)):
                            if nm & (1 << i):
                                cells[i] = None
                    cells = [_coerce(v) for v in cells[:width]]
                    prev = cells
                    out.append(cells)
    return out


def _queryable_visuals(metadata: dict) -> list[tuple[str, dict]]:
    visuals: list[tuple[str, dict]] = []
    for section in metadata.get("exploration", {}).get("sections", []):
        for c in section.get("visualContainers", []):
            cfg = c.get("config")
            if isinstance(cfg, str):
                try:
                    cfg = json.loads(cfg)
                except json.JSONDecodeError:
                    continue
            if not isinstance(cfg, dict):
                continue
            vid = cfg.get("name")
            single = cfg.get("singleVisual", {})
            if vid and single.get("prototypeQuery"):
                visuals.append((vid, single))
    return visuals


def _parse_axis(value: Any) -> dt.datetime | None:
    if isinstance(value, (int, float)) and value > 10_000_000_000:
        return dt.datetime.fromtimestamp(value / 1000.0, tz=dt.timezone.utc).replace(tzinfo=None)
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value.rstrip("Z"))
        except ValueError:
            pass
    return None


# ---------- public API: fetch only ----------

def fetch_responses(page_url: str) -> dict[str, Any]:
    """HTTP only — no decoding. Fetch the graph page, find the iframe, hit
    the PowerBI public API, return raw JSON for the report metadata and
    each visual's querydata response.

    Returns:
      {
        "page_url": str,
        "report_id": str | None,
        "metadata_json": str | None,
        "error": str | None,
        "visuals": [
          {"visual_id": str, "visual_title": str,
           "response_json": str | None, "error": str | None},
        ],
      }
    """
    result: dict[str, Any] = {
        "page_url": page_url, "report_id": None,
        "metadata_json": None, "error": None, "visuals": [],
    }

    page_body, _final, page_status = get(page_url)
    if page_status != 200:
        result["error"] = f"page fetch HTTP {page_status}"
        return result

    iframes = _find_iframes(page_url, page_body)
    if not iframes:
        result["error"] = "no PowerBI iframe found"
        return result

    report_id = _decode_report_id(iframes[0])
    result["report_id"] = report_id

    metadata = _http_json(
        f"{POWERBI_API_ROOT}/{report_id}/modelsAndExploration?preferReadOnlySession=true",
        report_id,
    )
    result["metadata_json"] = json.dumps(metadata)

    for visual_id, single in _queryable_visuals(metadata):
        refs = _plotted_refs(single)
        roles = _role_indices(single, refs)
        if not refs or not (roles["Y"] + roles["Y2"]):
            continue
        title = _visual_title(single, "")
        try:
            query = _clone_query(single["prototypeQuery"], refs)
            payload = _query_payload(report_id, metadata, visual_id, query)
            response = _http_json(
                f"{POWERBI_API_ROOT}/querydata?synchronous=true",
                report_id, payload,
            )
        except Exception as exc:
            result["visuals"].append({
                "visual_id": visual_id, "visual_title": title,
                "response_json": None, "error": repr(exc),
            })
            continue
        result["visuals"].append({
            "visual_id": visual_id, "visual_title": title,
            "response_json": json.dumps(response), "error": None,
        })
    return result


# ---------- public API: decode only ----------

def decode_response(metadata_json: str, visual_id: str, response_json: str) -> list[dict[str, Any]]:
    """Pure decode: given the metadata JSON, the visual id, and the visual's
    querydata response JSON, produce parsed rows. No HTTP.
    """
    metadata = json.loads(metadata_json)
    response = json.loads(response_json)

    # find this visual's singleVisual block
    target = None
    for vid, single in _queryable_visuals(metadata):
        if vid == visual_id:
            target = single
            break
    if target is None:
        return []

    refs = _plotted_refs(target)
    roles = _role_indices(target, refs)
    value_indices = roles["Y"] + roles["Y2"]
    if not refs or not value_indices:
        return []

    cells_rows = _decode_rows(response, len(refs))
    cat_idx = roles["Category"][0] if roles["Category"] else 0
    series_indices = roles["Series"]

    rows: list[dict[str, Any]] = []
    for cells in cells_rows:
        ts = _parse_axis(cells[cat_idx]) if cat_idx < len(cells) else None
        series_group = None
        if series_indices:
            parts = [str(cells[i]) for i in series_indices if i < len(cells) and cells[i] is not None]
            series_group = " / ".join(parts) if parts else None
        for vi in value_indices:
            raw_v = cells[vi] if vi < len(cells) else None
            value = raw_v if isinstance(raw_v, (int, float)) else None
            metric = _display_name(target, refs[vi])
            series = (
                f"{series_group} - {metric}" if series_group and len(value_indices) > 1
                else (series_group or metric)
            )
            rows.append({"timestamp": ts, "series": series, "value": value})
    return rows


# ---------- legacy combined API (kept for one-shot use; not bruin-backed) ----------

def scrape_powerbi(page_url: str) -> dict[str, Any]:
    """One-shot: fetch + decode in a single call. Convenience for ad-hoc use;
    bruin assets prefer fetch_responses + decode_response separately."""
    scraped_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
    result: dict[str, Any] = {
        "scraped_at": scraped_at, "page_url": page_url,
        "report_id": None, "metadata_json": None, "error": None, "visuals": [],
    }

    page_body, _final, page_status = get(page_url)
    if page_status != 200:
        result["error"] = f"page fetch HTTP {page_status}"
        return result

    iframes = _find_iframes(page_url, page_body)
    if not iframes:
        result["error"] = "no PowerBI iframe found"
        return result

    report_id = _decode_report_id(iframes[0])
    result["report_id"] = report_id

    metadata = _http_json(
        f"{POWERBI_API_ROOT}/{report_id}/modelsAndExploration?preferReadOnlySession=true",
        report_id,
    )
    result["metadata_json"] = json.dumps(metadata)

    for visual_id, single in _queryable_visuals(metadata):
        refs = _plotted_refs(single)
        roles = _role_indices(single, refs)
        value_indices = roles["Y"] + roles["Y2"]
        if not refs or not value_indices:
            continue

        try:
            query = _clone_query(single["prototypeQuery"], refs)
            payload = _query_payload(report_id, metadata, visual_id, query)
            response = _http_json(f"{POWERBI_API_ROOT}/querydata?synchronous=true", report_id, payload)
            cell_rows = _decode_rows(response, len(refs))
        except Exception as exc:
            result["visuals"].append({
                "visual_id": visual_id,
                "visual_title": _visual_title(single, ""),
                "response_json": None,
                "error": repr(exc),
                "rows": [],
            })
            continue

        title = _visual_title(single, "")
        cat_idx = roles["Category"][0] if roles["Category"] else 0
        series_indices = roles["Series"]

        rows: list[dict[str, Any]] = []
        for cells in cell_rows:
            ts = _parse_axis(cells[cat_idx]) if cat_idx < len(cells) else None
            series_group = None
            if series_indices:
                parts = [str(cells[i]) for i in series_indices if i < len(cells) and cells[i] is not None]
                series_group = " / ".join(parts) if parts else None
            for vi in value_indices:
                raw_v = cells[vi] if vi < len(cells) else None
                value = raw_v if isinstance(raw_v, (int, float)) else None
                metric = _display_name(single, refs[vi])
                series = (
                    f"{series_group} - {metric}" if series_group and len(value_indices) > 1
                    else (series_group or metric)
                )
                rows.append({"timestamp": ts, "series": series, "value": value})

        result["visuals"].append({
            "visual_id": visual_id,
            "visual_title": title,
            "response_json": json.dumps(response),
            "error": None,
            "rows": rows,
        })

    return result
