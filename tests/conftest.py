"""Independent minimal schema fixtures, deliberately without SQL constraints."""

import sqlite3
from contextlib import closing

import pytest

SCHEMA = """
PRAGMA user_version=18;
CREATE TABLE project(id INTEGER, name TEXT, location TEXT, created_at TEXT,
 modified_at TEXT, schema_version INTEGER);
CREATE TABLE sections(id INTEGER, name TEXT, surveyor TEXT, date TEXT,
 color TEXT, direction TEXT, quality REAL, created_at TEXT,
 gauge_shot_uuid TEXT, gauge_neighbour_uuid TEXT, reverse_parity INTEGER,
 azimuth_north TEXT, azimuth_correction REAL, azimuth_source TEXT,
 azimuth_epoch_year INTEGER);
CREATE TABLE shots(id INTEGER, section_id INTEGER, sequence_order INTEGER,
 azimuth_in REAL, azimuth_out REAL, length REAL, depth_in REAL, depth_out REAL,
 pitch_in REAL, pitch_out REAL, left_distance REAL, right_distance REAL,
 up_distance REAL, down_distance REAL, comment TEXT, kind INTEGER,
 marker_index INTEGER, temperature REAL, uuid TEXT);
CREATE TABLE station_comments(section_id INTEGER, station_index INTEGER, comment TEXT);
CREATE TABLE project_settings(key TEXT, value TEXT);
INSERT INTO project VALUES(7, 'Cave', NULL, '2026-01-01T00:00:00+00:00',
 '2026-01-02T00:00:00+00:00', 18);
INSERT INTO sections VALUES(42, 'Repeat', NULL, '2026-01-01', '#abc', 'in',
 1.5, '2026-01-01T00:00:00Z', NULL, NULL, 0, NULL, NULL, NULL, NULL);
INSERT INTO shots VALUES(99, 42, 0, 12.123456789, 14, 0, -1, 20, NULL, 90,
 NULL, 0, 2, 3, NULL, 0, 17, 23.5, NULL);
"""


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "survey ?#%.STALX"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript(SCHEMA)
    return path


def execute(path, sql, parameters=()):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(sql, parameters)
