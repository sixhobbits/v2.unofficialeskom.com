""" @bruin
name: raw.esp_loadshedding_fetch
connection: eskom_warehouse
materialization:
    type: table
    strategy: create+replace

tags:
    - hourly

description: |
    Stage-change events from the EskomSePush Google Sheet history.
    Each row is one stage-change event (not a time series — forward-fill
    in staging to get per-day max).

columns:
    - name: event_at
      type: TIMESTAMP
    - name: stage
      type: INTEGER
    - name: fetched_at
      type: TIMESTAMP
    - name: content_hash
      type: VARCHAR
@bruin """

import datetime as dt
import hashlib
import io
import csv
import urllib.request

import pandas as pd

_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1ZpX_twP8sFBOAU6t--Vvh1pWMYSvs60UXINuD5n-K08"
    "/gviz/tq?tqx=out:csv&sheet=EskomSePush_history"
)


def materialize() -> pd.DataFrame:
    with urllib.request.urlopen(_URL, timeout=20) as r:
        raw = r.read()

    content_hash = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)

    records = []
    for row in rows:
        try:
            event_at = pd.to_datetime(row["created_at"])
            stage = int(row["stage"])
        except (KeyError, ValueError):
            continue
        records.append({
            "event_at": event_at,
            "stage": stage,
            "fetched_at": now,
            "content_hash": content_hash,
        })

    print(f"  esp_loadshedding_fetch: {len(records)} events", flush=True)
    return pd.DataFrame(records, columns=["event_at", "stage", "fetched_at", "content_hash"])
