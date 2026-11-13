"""Native geographic metadata stays strict, immutable, and unadjusted."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from pydantic import ValidationError

from stalagmight_lib import DataValidationError
from stalagmight_lib import StalagmightFormatError
from stalagmight_lib import Survey
from stalagmight_lib import read_stalx
from tests.conftest import execute

GEOGRAPHIC_SCHEMA = """
CREATE TABLE zero_datums(id INTEGER, section_id INTEGER, station_index INTEGER,
 latitude REAL, longitude REAL, depth_reference REAL);
CREATE TABLE station_merges(id INTEGER, station_a_section INTEGER,
 station_a_index INTEGER, station_b_section INTEGER, station_b_index INTEGER,
 merged_at TEXT);
INSERT INTO zero_datums VALUES(1,42,0,0,0,-2);
INSERT INTO station_merges VALUES(1,42,0,42,1,'2026-01-01T00:00:00Z');
"""


@pytest.fixture
def geographic(database):
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.executescript(GEOGRAPHIC_SCHEMA)
    return database


def test_example_metadata_unchanged():
    path = Path(__file__).parent / "artifacts/stalagmight.stalx"
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns
    survey = read_stalx(path)
    assert len(survey.zero_datums) == 1
    assert len(survey.station_merges) == 36
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        for table in ("zero_datums", "station_merges"):
            rows = conn.execute(
                f"SELECT * FROM {table} ORDER BY id"  # noqa: S608 - fixed table names
            ).fetchall()
            records = getattr(survey, table)
            for record, row in zip(records, rows, strict=True):
                raw = dict(row)
                if table == "station_merges":
                    raw["merged_at"] = record.merged_at.fromisoformat(raw["merged_at"])
                assert record.model_dump() == raw
    assert Survey.model_validate_json(survey.model_dump_json()) == survey
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == mtime


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE zero_datums SET latitude=91",
        "UPDATE zero_datums SET longitude=-181",
        "UPDATE zero_datums SET latitude=1e999",
        "UPDATE zero_datums SET depth_reference=1e999",
        "UPDATE zero_datums SET id=1.5",
        "UPDATE zero_datums SET station_index=-1",
        "UPDATE zero_datums SET station_index=2",
        "UPDATE zero_datums SET section_id=999",
        "INSERT INTO zero_datums SELECT * FROM zero_datums",
        (
            "INSERT INTO zero_datums SELECT 2,section_id,station_index,latitude,"
            "longitude,depth_reference FROM zero_datums"
        ),
        "UPDATE station_merges SET station_a_section=999",
        "UPDATE station_merges SET station_b_section=999",
        "UPDATE station_merges SET station_a_index=2",
        "UPDATE station_merges SET station_b_index=-1",
        "UPDATE station_merges SET merged_at='2026-01-01T00:00:00'",
        "INSERT INTO station_merges SELECT * FROM station_merges",
    ],
)
def test_invalid_geographic_metadata(geographic, sql):
    execute(geographic, sql)
    with pytest.raises(DataValidationError):
        read_stalx(geographic)


@pytest.mark.parametrize("table", ["zero_datums", "station_merges"])
@pytest.mark.parametrize(
    "replacement",
    ["CREATE TABLE {table}(id INTEGER)", "CREATE VIEW {table} AS SELECT 1 AS id"],
)
def test_malformed_geographic_schema(geographic, table, replacement):
    execute(geographic, f"DROP TABLE {table}")
    execute(geographic, replacement.format(table=table))
    with pytest.raises(StalagmightFormatError):
        read_stalx(geographic)


def test_optional_tables_and_empty_station_zero(database, geographic):
    execute(geographic, "DELETE FROM shots")
    execute(geographic, "UPDATE station_merges SET station_b_index=0")
    survey = read_stalx(geographic)
    assert survey.zero_datums[0].station_index == 0
    with pytest.raises(ValidationError):
        survey.zero_datums[0].latitude = 1
    raw = json.loads(survey.model_dump_json())
    raw["zero_datums"][0]["station_index"] = 1
    with pytest.raises(ValidationError):
        Survey.model_validate_json(json.dumps(raw))
    execute(geographic, "DROP TABLE zero_datums")
    execute(geographic, "DROP TABLE station_merges")
    assert read_stalx(database).zero_datums == ()
    assert read_stalx(database).station_merges == ()


def test_geographic_queries_are_bulk_and_connections_close(geographic, monkeypatch):
    original = sqlite3.connect
    queries, connections = [], []

    def connect(*args, **kwargs):
        conn = original(*args, **kwargs)
        conn.set_trace_callback(queries.append)
        connections.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    read_stalx(geographic)
    count = len(queries)
    with closing(original(geographic)) as conn, conn:
        conn.execute("DELETE FROM station_merges")
        for index in range(100):
            conn.execute(
                "INSERT INTO station_merges VALUES(?,42,0,42,1,?)",
                (index, "2026-01-01T00:00:00Z"),
            )
    queries.clear()
    read_stalx(geographic)
    assert len(queries) == count
    assert sum('FROM "station_merges"' in query for query in queries) == 1
    assert sum('FROM "zero_datums"' in query for query in queries) == 1
    execute(geographic, "UPDATE zero_datums SET station_index=2")
    with pytest.raises(DataValidationError):
        read_stalx(geographic)
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")
