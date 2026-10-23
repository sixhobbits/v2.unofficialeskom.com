from datetime import datetime

import duckdb
import pandas as pd

from conftest import load_asset


COLUMNS = ['slug', 'response_hash', 'visual_id', 'visual_title', 'timestamp', 'series', 'value']


def test_batched_parser_preserves_rows_and_skips_failed_decode(tmp_path, monkeypatch):
    asset = load_asset('portal_powerbi.py')
    path = tmp_path / 'warehouse.duckdb'
    records = [
        ('demand', 'hash-a', 'visual-a', 'Demand', 'a', 'meta-a'),
        ('capacity', 'hash-b', 'visual-b', 'Capacity', 'b', 'meta-b'),
        ('broken', 'hash-c', 'visual-c', 'Broken', 'bad', 'meta-c'),
    ]
    with duckdb.connect(str(path)) as conn:
        conn.execute('CREATE SCHEMA raw')
        conn.execute('CREATE TABLE raw.portal_powerbi_content (slug VARCHAR, response_hash VARCHAR, visual_id VARCHAR, visual_title VARCHAR, response_json VARCHAR, metadata_json VARCHAR)')
        conn.executemany('INSERT INTO raw.portal_powerbi_content VALUES (?,?,?,?,?,?)', records)
    monkeypatch.setattr(asset, 'DB_PATH', path)
    decoded = {
        'a': [{'timestamp': datetime(2026, 10, 21, 12), 'series': 'Actual', 'value': 123.5},
              {'timestamp': datetime(2026, 10, 21, 13), 'series': 'Actual', 'value': 124.0}],
        'b': [{'timestamp': None, 'series': 'Installed', 'value': 45000.0}],
    }
    def decode(metadata, visual, response):
        if response == 'bad':
            raise ValueError('unreadable response')
        return decoded[response]
    monkeypatch.setattr(asset, 'decode_response', decode)
    expected = []
    for slug, response_hash, visual_id, title, response, metadata in records:
        for row in decoded.get(response, []):
            expected.append(dict(slug=slug, response_hash=response_hash, visual_id=visual_id,
                                 visual_title=title, **row))
    pd.testing.assert_frame_equal(asset.materialize(), pd.DataFrame(expected, columns=COLUMNS), check_dtype=False)


def test_empty_history_keeps_export_schema(tmp_path, monkeypatch):
    asset = load_asset('portal_powerbi.py')
    path = tmp_path / 'warehouse.duckdb'
    with duckdb.connect(str(path)) as conn:
        conn.execute('CREATE SCHEMA raw')
        conn.execute('CREATE TABLE raw.portal_powerbi_content (slug VARCHAR, response_hash VARCHAR, visual_id VARCHAR, visual_title VARCHAR, response_json VARCHAR, metadata_json VARCHAR)')
    monkeypatch.setattr(asset, 'DB_PATH', path)
    result = asset.materialize()
    assert result.empty
    assert list(result.columns) == COLUMNS
