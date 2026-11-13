# API reference

All public names below are exported from `stalagmight_lib`.

## Reader and parser

`read_stalx(filepath: str | Path) -> Survey` reads an existing regular `.stalx`
file (case-insensitive extension). It checks the SQLite signature, both version
markers, ordinary required tables and known columns, then validates all
supported records and relationships in a single read transaction. Additional
tables and columns are allowed. Optional `station_comments`, `project_settings`,
`zero_datums`, and `station_merges` tables may be absent; when present their
relevant columns must exist. Sections are ordered by ID, shots by sequence
within their section, comments by station index, and datums/merges by row ID.
Query count is independent of section count. Connections close on every exit.

`StalagmightParser(filepath)` is an eager facade. `filepath` is a `Path`, `data`
is a `Survey`, `sections` and `shots` are tuples, and `to_json() -> str`
serializes `data` with two-space indentation. There are no native writers or
lazy reads.

## Model hierarchy

| Model              | Fields                                                                                                                                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Survey`           | `schema_version: Literal[18] = 18`, `project: ProjectMetadata`, `sections: tuple[SurveySection, ...] = ()`, `zero_datums: tuple[ZeroDatum, ...] = ()`, `station_merges: tuple[StationMerge, ...] = ()` |
| `ProjectMetadata`  | `id: int`, `name: str`, `location: str \| None`, `created_at`, `modified_at`: aware `datetime`, `default_azimuth_reference: AzimuthReference \| None = None`                                           |
| `AzimuthReference` | `north: NorthReference`, `correction: float`, `source: CorrectionSource`, `epoch_year: int \| None = None`                                                                                             |
| `SurveySection`    | All section fields in the [format mapping](format.md), plus `shots: tuple[SurveyShot, ...] = ()` and `station_comments: tuple[StationComment, ...] = ()`                                               |
| `SurveyShot`       | All 19 shot fields in the [format mapping](format.md)                                                                                                                                                  |
| `StationComment`   | `section_id: int`, `station_index: int`, `comment: str \| None`                                                                                                                                        |
| `ZeroDatum`        | `id`, `section_id`, `station_index`: `int`; `latitude`, `longitude`, `depth_reference`: `float`                                                                                                        |
| `StationMerge`     | `id`, `station_a_section`, `station_a_index`, `station_b_section`, `station_b_index`: `int`; `merged_at`: aware `datetime`                                                                             |

All stored fields are required, including nullable fields, unless a default is
shown above. UUID fields accept UUID instances or valid UUID strings. Date
fields accept dates or ISO date strings; timestamps accept aware datetimes or
ISO strings with offsets. String enum fields accept their enums or exact tokens.
`kind` accepts `ShotKind` or a real integer discriminant. Collections are
tuples; JSON arrays deserialize to tuples. Models reject extra fields,
non-finite numbers, boolean measurements, numeric strings, and boolean or
fractional integer fields. Strict floats accept integer numeric values without
rounding measurements.

Models are frozen and nested models are revalidated. Pydantic's explicit bypass
APIs (`model_construct`, unvalidated `model_copy(update=...)`) are not
validation boundaries; use `model_validate` or `model_validate_json` for
external data.

`Survey.shots` flattens sections in tuple order.
`SurveyShot.start_station_index` and `end_station_index` are ordinary properties
returning `sequence_order` and `sequence_order + 1`. These properties are not
duplicated into JSON. `SurveySection.station_comment(index) -> str | None` looks
up a positional comment; no record and a nullable record both return `None`.

## Validation

- Identifiers and indices require real integers. Row IDs remain database IDs.
- Length and passage dimensions are nonnegative; zero is valid. Signed depths
  and finite temperatures are allowed. Azimuths lie in `[0, 360)`; nullable
  pitches lie in `[-90, 90]`. Other numeric metadata must be finite.
- SQLite `reverse_parity` must be exactly integer 0 or 1. The public model uses
  a strict boolean.
- Unknown enums, malformed UUIDs/dates and timestamps without timezones fail.
- Section IDs and shot row IDs must be unique. Shot IDs are unique survey-wide.
  Non-null UUIDs must be unique within a section. Duplicate names are allowed.
- Every shot/comment belongs to its containing section. Shot sequences must be
  contiguous from zero in tuple order. Comment indices are unique and range from
  0 to the section's shot count, inclusive.
- Depth discontinuities and depth changes exceeding length remain unchanged. No
  pitch inference, azimuth averaging, rounding, correction, or geometry runs.

## Enums

`ShotKind.NORMAL = 0`, `JUMP = 1`, `REFERENCE = 2` are integer enum members.
`SurveyDirection.IN = "in"`, `OUT = "out"`;
`NorthReference.MAGNETIC = "magnetic"`, `TRUE = "true"`, `GRID = "grid"`;
`CorrectionSource.UNKNOWN = "unknown"`, `FILE = "file"`, `IGRF = "igrf"`,
`MANUAL = "manual"` are string enum members. JSON uses their values.

## Errors and JSON Schema

All reader-specific errors inherit `StalagmightError`:

| Exception                | Meaning                                                                                         |
| ------------------------ | ----------------------------------------------------------------------------------------------- |
| `StalagmightFormatError` | Wrong extension/container, missing required table/column, or non-ordinary table                 |
| `UnsupportedSchemaError` | Unsupported, missing, or conflicting version markers                                            |
| `DatabaseReadError`      | SQLite opening or query failure, including corrupt database pages                               |
| `DataValidationError`    | Invalid stored records or relationships; includes table, row/section/sequence and field context |

Filesystem exceptions such as `FileNotFoundError`, `IsADirectoryError`, and
`PermissionError` propagate normally. Direct public model validation raises
Pydantic `ValidationError`.

```python
from stalagmight_lib import Survey

schema = Survey.model_json_schema()
# Includes nested models, enum values, nullable fields, UUID/date formats,
# required fields, forbidden extras, and numeric bounds.
```

Tuple ordering and cross-record rules are enforced by model validators and are
not fully expressible in JSON Schema. See the
[Pydantic model documentation](https://docs.pydantic.dev/latest/concepts/models/)
for the native validation and JSON APIs. SQLite's
[URI documentation](https://www.sqlite.org/uri.html) describes the read-only
connection mode used by the reader.

Geographic metadata validates unique row IDs, unique datum stations, finite
bounded coordinates, aware merge timestamps, and station references from zero
through each section's shot count. Reading it does not calculate geometry or
apply merges. See the README for the native-reader → OpenSpeleo adapter → shared
GeoJSON exporter boundary.
