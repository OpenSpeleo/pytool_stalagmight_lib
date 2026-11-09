import hashlib
import json
import shutil
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from stalagmight_lib import DatabaseReadError
from stalagmight_lib import DataValidationError
from stalagmight_lib import ShotKind
from stalagmight_lib import StalagMightFormatError
from stalagmight_lib import StalagMightParser
from stalagmight_lib import Survey
from stalagmight_lib import UnsupportedSchemaError
from stalagmight_lib import read_stalx
from tests.conftest import execute

EXAMPLE = Path(__file__).parent / "artifacts/example.stalx"
CHECKSUM = "e6f508f02257682be5f70f85029830f00b30d137cd1bba8db485d85b897df5a7"


def test_example_all_fields():
    before = EXAMPLE.stat().st_mtime_ns
    assert hashlib.sha256(EXAMPLE.read_bytes()).hexdigest() == CHECKSUM
    parser = StalagMightParser(EXAMPLE)
    survey = parser.data
    assert len(survey.sections) == 37
    assert len(survey.shots) == 532
    assert Counter(shot.kind for shot in survey.shots) == {0: 467, 1: 60, 2: 5}
    assert sum(shot.comment is not None for shot in survey.shots) == 2
    assert sum(len(section.station_comments) for section in survey.sections) == 74
    names = [section for section in survey.sections if section.name == "Mainline North"]
    assert len(names) == 2
    assert names[0].id != names[1].id
    with closing(sqlite3.connect(EXAMPLE)) as conn:
        conn.row_factory = sqlite3.Row
        assert [s.id for s in survey.sections] == [
            row[0] for row in conn.execute("SELECT id FROM sections ORDER BY id")
        ]
        for section in survey.sections:
            row = dict(
                conn.execute(
                    "SELECT * FROM sections WHERE id=?", (section.id,)
                ).fetchone()
            )
            for field, value in row.items():
                actual = getattr(section, field)
                if field == "date" and value is not None:
                    assert actual == date.fromisoformat(value)
                elif field == "created_at":
                    assert actual.isoformat() == value
                elif field in {"gauge_shot_uuid", "gauge_neighbour_uuid"} and value:
                    assert actual == UUID(value)
                else:
                    assert actual == value
            rows = list(
                conn.execute(
                    "SELECT * FROM shots WHERE section_id=? ORDER BY sequence_order",
                    (section.id,),
                )
            )
            assert len(rows) == len(section.shots)
            for shot, row in zip(section.shots, rows, strict=True):
                for field, value in dict(row).items():
                    assert getattr(shot, field) == (
                        UUID(value) if field == "uuid" and value else value
                    )
                assert shot.start_station_index == shot.sequence_order
                assert shot.end_station_index == shot.sequence_order + 1
            for comment in section.station_comments:
                assert (
                    section.station_comment(comment.station_index)
                    == conn.execute(
                        "SELECT comment FROM station_comments "
                        "WHERE section_id=? AND station_index=?",
                        (section.id, comment.station_index),
                    ).fetchone()[0]
                )
    comments = {
        shot.id: shot.comment for shot in survey.shots if shot.comment is not None
    }
    assert comments == {408: "Yellow line repair", 474: "Passage West"}
    inconsistent = next(shot for shot in survey.shots if shot.id == 282)
    assert (inconsistent.length, inconsistent.depth_in, inconsistent.depth_out) == (
        0.15,
        12.21,
        9.86,
    )
    assert Survey.model_validate_json(parser.to_json()) == survey
    assert parser.sections == survey.sections
    assert parser.shots == survey.shots
    assert EXAMPLE.stat().st_mtime_ns == before
    assert hashlib.sha256(EXAMPLE.read_bytes()).hexdigest() == CHECKSUM


def test_synthetic_roundtrip(database):
    survey = read_stalx(database)
    shot = survey.shots[0]
    assert shot.left_distance is None
    assert shot.right_distance == 0
    assert shot.up_distance == 2
    assert shot.depth_in == -1
    assert shot.temperature == 23.5
    assert shot.marker_index == 17
    assert shot.azimuth_in == 12.123456789
    assert Survey.model_validate_json(survey.model_dump_json()) == survey
    schema = Survey.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["ShotKind"]["enum"] == [0, 1, 2]
    assert (
        schema["$defs"]["SurveyShot"]["properties"]["uuid"]["anyOf"][0]["format"]
        == "uuid"
    )
    with pytest.raises(ValidationError, match="frozen"):
        shot.length = 7


@pytest.mark.parametrize("text", [None, "", "  café 洞穴\nsecond line\n "])
def test_comments(database, text):
    execute(database, "UPDATE shots SET comment=?", (text,))
    for index in (0, 1):
        execute(
            database, "INSERT INTO station_comments VALUES(42, ?, ?)", (index, text)
        )
    section = read_stalx(database).sections[0]
    assert section.shots[0].comment == text
    assert section.station_comment(0) == text
    assert section.station_comment(1) == text
    assert section.station_comment(2) is None
    assert len(section.station_comments) == 2


@pytest.mark.parametrize("kind", [0, 1, 2])
def test_kinds(database, kind):
    execute(database, "UPDATE shots SET kind=?", (kind,))
    assert read_stalx(database).shots[0].kind is ShotKind(kind)


def test_ordering_and_identity(database):
    execute(
        database,
        "UPDATE shots SET sequence_order=1, uuid=?",
        ("f26c8521-2164-425d-b967-a4a4a874b69c",),
    )
    execute(
        database,
        (
            "INSERT INTO shots SELECT 100,section_id,0,azimuth_in,azimuth"
            "_out,length,depth_in,depth_out,pitch_in,pitch_out,left_dista"
            "nce,right_distance,up_distance,down_distance,comment,kind,ma"
            "rker_index,temperature,NULL FROM shots"
        ),
    )
    execute(
        database,
        (
            "INSERT INTO sections SELECT 9999999999,name,surveyor,date,co"
            "lor,direction,quality,created_at,gauge_shot_uuid,gauge_neigh"
            "bour_uuid,reverse_parity,azimuth_north,azimuth_correction,az"
            "imuth_source,azimuth_epoch_year FROM sections"
        ),
    )
    survey = read_stalx(database)
    assert [s.id for s in survey.shots] == [100, 99]
    assert [s.id for s in survey.sections] == [42, 9999999999]
    assert survey.sections[0].name == survey.sections[1].name
    assert survey.sections[1].shots == ()
    execute(database, "DELETE FROM shots")
    assert read_stalx(database).shots == ()
    execute(database, "DELETE FROM sections")
    assert read_stalx(database).sections == ()


@pytest.mark.parametrize(
    ("source", "expected", "epoch"),
    [
        ("unknown", "unknown", None),
        ("manual", "manual", None),
        ("file_declared", "file", None),
        ({"igrf_auto": {"epoch_year": 2026}}, "igrf", 2026),
    ],
)
def test_bearing_metadata(database, source, expected, epoch):
    execute(
        database,
        (
            'UPDATE sections SET azimuth_north="grid", '
            'azimuth_correction=-3.25, azimuth_source="igrf", '
            "azimuth_epoch_year=2026, reverse_parity=1, "
            "gauge_shot_uuid=?, gauge_neighbour_uuid=?"
        ),
        (
            "f26c8521-2164-425d-b967-a4a4a874b69c",
            "c7a8a0ce-771e-4ba2-a7fa-a7bcfe84f7d3",
        ),
    )
    execute(
        database,
        "INSERT INTO project_settings VALUES(?, ?)",
        (
            "default_azimuth_reference",
            json.dumps({"north": "magnetic", "correction": 2.25, "source": source}),
        ),
    )
    survey = read_stalx(database)
    ref = survey.project.default_azimuth_reference
    assert (ref.north, ref.correction, ref.source, ref.epoch_year) == (
        "magnetic",
        2.25,
        expected,
        epoch,
    )
    assert survey.sections[0].azimuth_correction == -3.25
    assert survey.sections[0].reverse_parity is True
    assert survey.shots[0].azimuth_in == 12.123456789
    assert Survey.model_validate_json(survey.model_dump_json()) == survey


@pytest.mark.parametrize("table", ["station_comments", "project_settings"])
def test_optional_tables(database, table):
    execute(database, f"DROP TABLE {table}")
    assert read_stalx(database)


@pytest.mark.parametrize(
    ("sql", "error", "match"),
    [
        ("PRAGMA user_version=17", UnsupportedSchemaError, "user_version=17"),
        ("PRAGMA user_version=19", UnsupportedSchemaError, "user_version=19"),
        ("PRAGMA user_version=0", UnsupportedSchemaError, "user_version=0"),
        ("UPDATE project SET schema_version=19", UnsupportedSchemaError, "conflicts"),
        (
            "ALTER TABLE project DROP COLUMN schema_version",
            UnsupportedSchemaError,
            "schema_version",
        ),
        ("DROP TABLE shots", StalagMightFormatError, "shots"),
        (
            "ALTER TABLE shots DROP COLUMN temperature",
            StalagMightFormatError,
            "temperature",
        ),
        (
            "ALTER TABLE station_comments DROP COLUMN comment",
            StalagMightFormatError,
            "comment",
        ),
        (
            "ALTER TABLE project_settings DROP COLUMN value",
            StalagMightFormatError,
            "value",
        ),
        ("DELETE FROM project", DataValidationError, "exactly one"),
        (
            "INSERT INTO project SELECT * FROM project",
            DataValidationError,
            "exactly one",
        ),
        ("UPDATE shots SET section_id=43", DataValidationError, "orphan section_id"),
        (
            'INSERT INTO station_comments VALUES(43,0,"x")',
            DataValidationError,
            "orphan",
        ),
        (
            'INSERT INTO station_comments VALUES(42,2,"x")',
            DataValidationError,
            "station_index",
        ),
        (
            'INSERT INTO station_comments VALUES(42,-1,"x")',
            DataValidationError,
            "station_index",
        ),
        (
            'INSERT INTO station_comments VALUES(42,0,"x"),(42,0,"y")',
            DataValidationError,
            "duplicate",
        ),
        (
            "INSERT INTO sections SELECT * FROM sections",
            DataValidationError,
            "duplicate id",
        ),
        (
            "INSERT INTO shots SELECT * FROM shots",
            DataValidationError,
            "sequence_order",
        ),
        ("UPDATE shots SET sequence_order=1", DataValidationError, "sequence_order"),
        ("UPDATE shots SET sequence_order=-1", DataValidationError, "sequence_order"),
        ("UPDATE sections SET reverse_parity=2", DataValidationError, "reverse_parity"),
        (
            'UPDATE sections SET reverse_parity="yes"',
            DataValidationError,
            "reverse_parity",
        ),
        ('UPDATE sections SET date="2026-02-30"', DataValidationError, "date"),
        (
            'UPDATE sections SET created_at="2026-01-01"',
            DataValidationError,
            "created_at",
        ),
        ('UPDATE sections SET direction="sideways"', DataValidationError, "direction"),
        (
            'UPDATE sections SET azimuth_north="north"',
            DataValidationError,
            "azimuth_north",
        ),
        (
            'UPDATE sections SET azimuth_source="auto"',
            DataValidationError,
            "azimuth_source",
        ),
        ("UPDATE shots SET kind=3", DataValidationError, "kind"),
        ('UPDATE shots SET uuid=""', DataValidationError, "uuid"),
        ("UPDATE shots SET id=1.5", DataValidationError, "id"),
        ('UPDATE shots SET length="NaN"', DataValidationError, "length"),
        ("UPDATE shots SET length=-1", DataValidationError, "length"),
        ("UPDATE shots SET azimuth_in=360", DataValidationError, "azimuth_in"),
        ("UPDATE shots SET azimuth_out=-1", DataValidationError, "azimuth_out"),
        ("UPDATE shots SET pitch_in=-91", DataValidationError, "pitch_in"),
        ("UPDATE shots SET left_distance=-1", DataValidationError, "left_distance"),
        ("UPDATE shots SET comment=zeroblob(4)", DataValidationError, "comment"),
    ],
)
def test_invalid_database(database, sql, error, match):
    execute(database, sql)
    with pytest.raises(error, match=match):
        read_stalx(database)


@pytest.mark.parametrize(
    "field",
    ["length", "depth_in", "depth_out", "pitch_in", "temperature", "left_distance"],
)
def test_nonfinite(database, field):
    execute(
        database,
        f"UPDATE shots SET {field}=?",  # noqa: S608 - parametrized constant fields
        (float("inf"),),
    )
    with pytest.raises(DataValidationError, match=field):
        read_stalx(database)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", True),
        ("id", 1.0),
        ("id", "1"),
        ("length", True),
        ("length", "2"),
        ("kind", True),
        ("kind", 1.0),
        ("kind", "1"),
        ("uuid", 42),
        ("unknown", 1),
    ],
)
def test_public_forbidden_coercions(database, field, value):
    shot = read_stalx(database).shots[0]
    data = shot.model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        type(shot).model_validate(data)
    with pytest.raises(ValidationError):
        type(shot).model_validate_json(
            json.dumps({**shot.model_dump(mode="json"), field: value})
        )


def test_duplicate_uuid(database):
    execute(database, 'UPDATE shots SET uuid="f26c8521-2164-425d-b967-a4a4a874b69c"')
    execute(
        database,
        (
            "INSERT INTO shots SELECT 100,section_id,1,azimuth_in,azimuth"
            "_out,length,depth_in,depth_out,pitch_in,pitch_out,left_dista"
            "nce,right_distance,up_distance,down_distance,comment,kind,ma"
            "rker_index,temperature,uuid FROM shots"
        ),
    )
    with pytest.raises(DataValidationError, match="duplicate uuid"):
        read_stalx(database)
    execute(database, "UPDATE shots SET uuid=NULL")
    assert len(read_stalx(database).shots) == 2


@pytest.mark.parametrize(
    "value",
    [
        "invalid",
        "null",
        "[]",
        "{}",
        '{"north":"grid","correction":1,"source":{"other":{}}}',
        '{"north":"grid","correction":1,"source":{"igrf_auto":{}}}',
    ],
)
def test_invalid_project_reference(database, value):
    execute(
        database,
        'INSERT INTO project_settings VALUES("default_azimuth_reference",?)',
        (value,),
    )
    with pytest.raises(DataValidationError, match="project_settings"):
        read_stalx(database)


def test_paths_and_containers(database, tmp_path):
    with pytest.raises(FileNotFoundError):
        read_stalx(tmp_path / "missing.stalx")
    with pytest.raises(IsADirectoryError):
        read_stalx(tmp_path)
    wrong = tmp_path / "wrong.txt"
    shutil.copyfile(database, wrong)
    with pytest.raises(StalagMightFormatError, match="extension"):
        read_stalx(wrong)
    wrong = tmp_path / "wrong.stalx"
    wrong.write_bytes(b"not sqlite")
    with pytest.raises(StalagMightFormatError, match="signature"):
        read_stalx(wrong)
    wrong.write_bytes(b"SQLite format 3\0" + b"bad" * 100)
    with pytest.raises(DatabaseReadError):
        read_stalx(wrong)
    wrong.unlink()
    with closing(sqlite3.connect(wrong)) as conn, conn:
        conn.execute("CREATE TABLE arbitrary(id)")
    with pytest.raises(UnsupportedSchemaError):
        read_stalx(wrong)


def test_additional_columns_and_tables(database):
    execute(database, "ALTER TABLE shots ADD COLUMN extra TEXT")
    execute(database, "CREATE TABLE ignored(data)")
    execute(database, 'INSERT INTO project_settings VALUES("ignored","not JSON")')
    assert read_stalx(database)


def test_ordinary_table_required(database):
    execute(database, "DROP TABLE station_comments")
    execute(
        database,
        (
            "CREATE VIEW station_comments AS SELECT 42 AS section_id,0 AS"
            ' station_index,"text" AS comment'
        ),
    )
    with pytest.raises(StalagMightFormatError, match="ordinary table"):
        read_stalx(database)


def test_connection_cleanup_and_bulk_queries(database, monkeypatch):
    original = sqlite3.connect
    connections, queries = [], []

    def connect(*args, **kwargs):
        assert args[0].endswith("?mode=ro")
        conn = original(*args, **kwargs)
        connections.append(conn)
        conn.set_trace_callback(queries.append)
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)
    read_stalx(database)
    count = len(queries)
    with closing(original(database)) as conn, conn:
        for index in range(100):
            conn.execute(
                (
                    "INSERT INTO sections SELECT ?,name,surveyor,date,color,direc"
                    "tion,quality,created_at,gauge_shot_uuid,gauge_neighbour_uuid"
                    ",reverse_parity,azimuth_north,azimuth_correction,azimuth_sou"
                    "rce,azimuth_epoch_year FROM sections WHERE id=42"
                ),
                (1000 + index,),
            )
    queries.clear()
    read_stalx(database)
    assert len(queries) == count
    assert queries.count("BEGIN") == 1
    with closing(original(database)) as conn, conn:
        conn.execute("UPDATE shots SET length=-1")
    with pytest.raises(DataValidationError):
        read_stalx(database)
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")


@pytest.mark.parametrize(
    "relationship",
    [
        "shot_membership",
        "comment_membership",
        "duplicate_shot_id",
        "duplicate_section_id",
        "duplicate_shot_id_across_sections",
    ],
)
def test_public_relationship_validation(database, relationship):
    survey = read_stalx(database)
    raw = json.loads(survey.model_dump_json())
    section = raw["sections"][0]
    if relationship == "shot_membership":
        section["shots"][0]["section_id"] = 1
    elif relationship == "comment_membership":
        section["station_comments"] = [
            {"section_id": 1, "station_index": 0, "comment": ""}
        ]
    elif relationship == "duplicate_shot_id":
        section["shots"].append({**section["shots"][0], "sequence_order": 1})
    elif relationship == "duplicate_section_id":
        raw["sections"].append(section.copy())
    else:
        other = {
            **section,
            "id": 43,
            "shots": [{**section["shots"][0], "section_id": 43}],
        }
        raw["sections"].append(other)
    with pytest.raises(ValidationError):
        Survey.model_validate_json(json.dumps(raw))


def test_uuid_identity_is_section_scoped(database):
    execute(database, 'UPDATE shots SET uuid="f26c8521-2164-425d-b967-a4a4a874b69c"')
    execute(
        database,
        "INSERT INTO sections SELECT 43,name,surveyor,date,color,direction,quality,"
        "created_at,gauge_shot_uuid,gauge_neighbour_uuid,reverse_parity,"
        "azimuth_north,azimuth_correction,azimuth_source,azimuth_epoch_year "
        "FROM sections",
    )
    execute(
        database,
        "INSERT INTO shots SELECT 100,43,0,azimuth_in,azimuth_out,length,depth_in,"
        "depth_out,pitch_in,pitch_out,left_distance,right_distance,up_distance,"
        "down_distance,comment,kind,marker_index,temperature,uuid FROM shots",
    )
    assert len(read_stalx(database).shots) == 2


def test_duplicate_project_setting(database):
    for _ in range(2):
        execute(
            database,
            'INSERT INTO project_settings VALUES("default_azimuth_reference",?)',
            ('{"north":"true","correction":0,"source":"manual"}',),
        )
    with pytest.raises(DataValidationError, match="duplicate key"):
        read_stalx(database)


def test_empty_section_station_zero(database):
    execute(database, "DELETE FROM shots")
    execute(database, 'INSERT INTO station_comments VALUES(42,0,"initial")')
    assert read_stalx(database).sections[0].station_comment(0) == "initial"
