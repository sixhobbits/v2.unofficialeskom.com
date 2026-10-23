""" @bruin
name: raw.portal_powerbi
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

parameters:
    enforce_schema: true

depends:
    - raw.portal_powerbi_content

description: |
    Parsed generic portal PowerBI points, decoded from raw.portal_powerbi_
    content. Pure transform — no HTTP. One row per (slug, response_hash,
    timestamp, series). timestamp is NULL for non-temporal visuals; the
    series/value still land in the table.

columns:
    - name: slug
      type: VARCHAR
    - name: response_hash
      type: VARCHAR
    - name: visual_id
      type: VARCHAR
    - name: visual_title
      type: VARCHAR
    - name: timestamp
      type: TIMESTAMP
    - name: series
      type: VARCHAR
    - name: value
      type: DOUBLE
@bruin """

from pathlib import Path

import duckdb
import pandas as pd

from eskom_portal.powerbi_scrape import decode_response

DB_PATH = Path(__file__).resolve().parents[3] / "warehouse" / "eskom.duckdb"


def materialize() -> pd.DataFrame:
    # Keep historical revisions, but decode one payload at a time. The previous
    # all-history list of dictionaries exceeded small production hosts' memory.
    # Object-typed metadata columns share each payload's strings across its rows.
    columns = ["slug", "response_hash", "visual_id", "visual_title",
               "timestamp", "series", "value"]
    frames = []
    with duckdb.connect(str(DB_PATH), read_only=True,
                        config={"threads": 1, "memory_limit": "512MB"}) as conn:
        cursor = conn.execute(
            "SELECT slug, response_hash, visual_id, visual_title, response_json, metadata_json "
            "FROM raw.portal_powerbi_content"
        )
        while batch := cursor.fetchmany(1):
            slug, response_hash, visual_id, visual_title, response_json, metadata_json = batch[0]
            try:
                decoded = decode_response(metadata_json, visual_id, response_json)
            except Exception:
                continue
            if not decoded:
                continue
            frame = pd.DataFrame.from_records(decoded, columns=["timestamp", "series", "value"])
            for name, value in [("slug", slug), ("response_hash", response_hash),
                                ("visual_id", visual_id), ("visual_title", visual_title)]:
                frame[name] = pd.Series(value, index=frame.index, dtype=object)
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=columns)
    result = pd.concat(frames, ignore_index=True)[columns]
    # Match whole-frame inference when a non-temporal visual contains only nulls.
    result["timestamp"] = pd.to_datetime(result["timestamp"])
    return result
