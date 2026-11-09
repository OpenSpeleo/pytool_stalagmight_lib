"""Read schema-18 SQLite surveys in one read-only transaction."""

import json
import sqlite3
import stat
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from pydantic import ValidationError

from stalagmight_lib.exceptions import DatabaseReadError
from stalagmight_lib.exceptions import DataValidationError
from stalagmight_lib.exceptions import StalagMightFormatError
from stalagmight_lib.exceptions import UnsupportedSchemaError
from stalagmight_lib.section import StationComment
from stalagmight_lib.section import SurveySection
from stalagmight_lib.shot import SurveyShot
from stalagmight_lib.survey import AzimuthReference
from stalagmight_lib.survey import ProjectMetadata
from stalagmight_lib.survey import StationMerge
from stalagmight_lib.survey import Survey
from stalagmight_lib.survey import ZeroDatum

PROJECT_COLUMNS = (
    "id",
    "name",
    "location",
    "created_at",
    "modified_at",
    "schema_version",
)
SECTION_COLUMNS = tuple(
    name
    for name in SurveySection.model_fields
    if name not in {"shots", "station_comments"}
)
SHOT_COLUMNS = tuple(SurveyShot.model_fields)
COMMENT_COLUMNS = tuple(StationComment.model_fields)


def _columns(connection, table, columns, *, optional=False):
    record = connection.execute(
        "SELECT type, sql FROM sqlite_master WHERE name = ?", (table,)
    ).fetchone()
    if record is None and optional:
        return False
    if (
        record is None
        or record[0] != "table"
        or record[1] is None
        or not record[1].lstrip().upper().startswith("CREATE TABLE")
    ):
        raise StalagMightFormatError(f"{table}: expected an ordinary table")
    # Names below are library constants, never supplied by the file or caller.
    available = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
    missing = set(columns) - available
    if missing:
        if table == "project" and "schema_version" in missing:
            raise UnsupportedSchemaError(
                "project.schema_version is missing; expected 18"
            )
        raise StalagMightFormatError(f"{table}: missing columns {sorted(missing)}")
    return True


def _rows(connection, table, columns, order):
    selected = ", ".join(f'"{column}"' for column in columns)
    return [
        dict(row)
        for row in connection.execute(
            f'SELECT {selected} FROM "{table}" ORDER BY {order}'  # noqa: S608 - library constants
        )
    ]


def _validate(model, record, context):
    try:
        return model.model_validate(record)
    except ValidationError as exc:
        raise DataValidationError(f"{context}: {exc}") from exc


def _default_reference(connection):
    rows = connection.execute(
        "SELECT value FROM project_settings WHERE key = ?",
        ("default_azimuth_reference",),
    ).fetchall()
    context = "project_settings key default_azimuth_reference"
    if len(rows) > 1:
        raise DataValidationError(f"{context}: duplicate key")
    if not rows:
        return None
    # Native serde serializes CorrectionSource differently from section tokens.
    # Decode only that native wire shape; public JSON uses the flat model.
    try:
        value = _native_reference(rows[0][0])
    except (ValueError, TypeError) as exc:
        raise DataValidationError(f"{context}: {exc}") from exc
    return _validate(AzimuthReference, value, context)


def _native_reference(raw):
    if not isinstance(raw, str):
        raise TypeError("value must be JSON text")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise TypeError("value must be a JSON object")
    source = value.get("source")
    if source == "file_declared":
        value["source"] = "file"
    elif isinstance(source, dict):
        if set(source) != {"igrf_auto"}:
            raise ValueError("unrecognised source variant")
        payload = source["igrf_auto"]
        if not isinstance(payload, dict) or set(payload) != {"epoch_year"}:
            raise ValueError("igrf_auto requires epoch_year")
        if "epoch_year" in value:
            raise ValueError("epoch_year must occur only inside igrf_auto")
        value["source"] = "igrf"
        value["epoch_year"] = payload["epoch_year"]
    return value


def _read_project(connection, settings_present):
    projects = _rows(connection, "project", PROJECT_COLUMNS, "id")
    if len(projects) != 1:
        raise DataValidationError(
            f"project: expected exactly one row, found {len(projects)}"
        )
    project = projects[0]
    project_version = project.pop("schema_version")
    if type(project_version) is not int or project_version != 18:
        raise UnsupportedSchemaError(
            f"project.schema_version={project_version!r} conflicts with user_version=18"
        )
    project["default_azimuth_reference"] = (
        _default_reference(connection) if settings_present else None
    )
    return _validate(ProjectMetadata, project, f"project row {project['id']}")


def _read_geographic_metadata(connection):
    geographic = {}
    for table, model in (("zero_datums", ZeroDatum), ("station_merges", StationMerge)):
        columns = tuple(model.model_fields)
        if _columns(connection, table, columns, optional=True):
            geographic[table] = tuple(
                _validate(model, row, f"{table} row {row['id']}")
                for row in _rows(connection, table, columns, "id")
            )
    return geographic


def _read(connection):
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version != 18:
        raise UnsupportedSchemaError(f"PRAGMA user_version={version}; expected 18")
    _columns(connection, "project", PROJECT_COLUMNS)
    _columns(connection, "sections", SECTION_COLUMNS)
    _columns(connection, "shots", SHOT_COLUMNS)
    comments_present = _columns(
        connection, "station_comments", COMMENT_COLUMNS, optional=True
    )
    settings_present = _columns(
        connection, "project_settings", ("key", "value"), optional=True
    )
    geographic = _read_geographic_metadata(connection)
    metadata = _read_project(connection, settings_present)
    section_rows = _rows(connection, "sections", SECTION_COLUMNS, "id")
    sections = {}
    for row in section_rows:
        parity = row["reverse_parity"]
        if type(parity) is not int or parity not in (0, 1):
            raise DataValidationError(
                f"sections row {row['id']} reverse_parity: "
                "expected SQLite integer 0 or 1"
            )
        row["reverse_parity"] = bool(parity)
        section = _validate(SurveySection, row, f"sections row {row['id']}")
        if section.id in sections:
            raise DataValidationError(f"sections row {section.id}: duplicate id")
        sections[section.id] = section
    shots, comments = defaultdict(list), defaultdict(list)
    for row in _rows(
        connection, "shots", SHOT_COLUMNS, "section_id, sequence_order, id"
    ):
        context = (
            f"shots row {row['id']} section {row['section_id']} "
            f"sequence {row['sequence_order']}"
        )
        shot = _validate(SurveyShot, row, context)
        if shot.section_id not in sections:
            raise DataValidationError(f"{context}: orphan section_id")
        shots[shot.section_id].append(shot)
    if comments_present:
        for row in _rows(
            connection, "station_comments", COMMENT_COLUMNS, "section_id, station_index"
        ):
            context = (
                f"station_comments section {row['section_id']} "
                f"station {row['station_index']}"
            )
            comment = _validate(StationComment, row, context)
            if comment.section_id not in sections:
                raise DataValidationError(f"{context}: orphan section_id")
            comments[comment.section_id].append(comment)
    complete = tuple(
        _validate(
            SurveySection,
            {
                **section.model_dump(),
                "shots": tuple(shots[section.id]),
                "station_comments": tuple(comments[section.id]),
            },
            f"sections row {section.id}",
        )
        for section in sections.values()
    )
    return _validate(
        Survey, {"project": metadata, "sections": complete, **geographic}, "survey"
    )


def read_stalx(filepath: str | Path) -> Survey:
    """Read a complete supported survey without modifying its source file."""
    path = Path(filepath)
    mode = path.stat().st_mode  # Preserve ordinary filesystem exceptions.
    if stat.S_ISDIR(mode):
        raise IsADirectoryError(path)
    if not stat.S_ISREG(mode):
        raise StalagMightFormatError(f"{path}: expected a regular file")
    if path.suffix.lower() != ".stalx":
        raise StalagMightFormatError(f"{path}: expected a .stalx extension")
    with path.open("rb") as source:
        if source.read(16) != b"SQLite format 3\x00":
            raise StalagMightFormatError(f"{path}: missing SQLite signature")
    try:
        with closing(
            sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        ) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            return _read(conn)
    except sqlite3.Error as exc:
        raise DatabaseReadError(f"{path}: {exc}") from exc


class StalagMightParser:
    """Eager convenience facade for :func:`read_stalx`."""

    def __init__(self, filepath: str | Path):
        self.filepath = Path(filepath)
        self.data = read_stalx(self.filepath)

    @property
    def sections(self) -> tuple[SurveySection, ...]:
        return self.data.sections

    @property
    def shots(self) -> tuple[SurveyShot, ...]:
        return self.data.shots

    def to_json(self) -> str:
        return self.data.model_dump_json(indent=2)
