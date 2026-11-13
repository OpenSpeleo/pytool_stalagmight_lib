# Schema-18 format reference

## Container and evidence

`.stalx` is a SQLite database with the `SQLite format 3` signature. The reader
requires both `PRAGMA user_version` and `project.schema_version` to equal 18. No
migrations or repairs run. Required ordinary tables are `project`, `sections`,
and `shots`; exactly one project row is required. Extra schema-18 tables and
columns are allowed, without becoming public model fields. Optional ordinary
`station_comments`, `project_settings`, `zero_datums`, and `station_merges`
tables may be absent.

The checked-in `tests/artifacts/example.stalx` is 217,088 bytes, with 19 tables.
Observed fixture facts: both version markers are 18; SQLite integrity and
foreign-key checks pass; 37 sections contain 532 shots (467 normal, 60 jump, 5
reference), 2 shot comments, and 74 station comments. Section IDs are
noncontiguous and two distinct sections are named “Mainline North”. Nullable
passage dimensions coexist with stored zeros. There are depth discontinuities.

Semantics were compared against the native Stalagmight application. Inspected
source paths are given relative to that upstream repository; this reference
needs no sibling checkout:

- `src-tauri/crates/persistence/src/persistence/sqlite.rs`: schema version and
  schema-12 positive-down pitch convention.
- `src-tauri/crates/persistence/src/persistence/sqlite/schema.rs`: table
  creation and migrations, including UUID, kind, gauge and north-reference
  fields.
- `src-tauri/crates/persistence/src/persistence/sqlite/read.rs` and `write.rs`:
  persisted columns, ordering, runtime IDs and project-setting wire format.
- `src-tauri/crates/models/src/shot.rs`: kind discriminants, metres, degrees,
  Celsius, signed depths and two forward azimuth readings.
- `src-tauri/crates/models/src/section.rs`, `station.rs` and
  `azimuth_reference.rs`: section metadata, positional stations, north tokens,
  provenance and correction sign.

These are source-confirmed meanings. The example alone does not demonstrate
non-null north metadata or all allowable nullable/positive measurement values;
synthetic tests cover those. The reader deliberately rejects invalid records
that the application might sanitize or default, and preserves database row IDs
rather than generating runtime shot IDs.

## Complete supported column mapping

The SQL type and nullability below describe the native fixture declarations.
SQLite affinity does not guarantee runtime storage types: the reader validates
actual values. INTEGER PRIMARY KEY IDs are required real integers by the API. A
nullable column maps to the listed Python type **or None**. All names are
retained verbatim, except the project schema version is on `Survey`.

### `project`

| Column           | Declared SQL type | SQL nullable     | Python type   | Meaning / unit                                          |
| ---------------- | ----------------- | ---------------- | ------------- | ------------------------------------------------------- |
| `id`             | INTEGER           | No (primary key) | `int`         | Database row identity; sections may be noncontiguous.   |
| `name`           | TEXT              | No               | `str`         | Project/section name; section names need not be unique. |
| `location`       | TEXT              | Yes              | `str`         | Project location text.                                  |
| `created_at`     | TEXT              | No               | `datetime`    | ISO timestamp with timezone, preserved instant.         |
| `modified_at`    | TEXT              | No               | `datetime`    | ISO timestamp with timezone, preserved instant.         |
| `schema_version` | INTEGER           | No               | `Literal[18]` | Must match PRAGMA user_version=18; moved to Survey.     |

### `sections`

| Column                 | Declared SQL type | SQL nullable     | Python type        | Meaning / unit                                              |
| ---------------------- | ----------------- | ---------------- | ------------------ | ----------------------------------------------------------- |
| `id`                   | INTEGER           | No (primary key) | `int`              | Database row identity; sections may be noncontiguous.       |
| `name`                 | TEXT              | Yes              | `str`              | Project/section name; section names need not be unique.     |
| `surveyor`             | TEXT              | Yes              | `str`              | Surveyor text.                                              |
| `date`                 | TEXT              | Yes              | `date`             | ISO calendar date YYYY-MM-DD.                               |
| `color`                | TEXT              | No               | `str`              | Stored color text, no normalization.                        |
| `direction`            | TEXT              | No               | `SurveyDirection`  | TEXT in or out.                                             |
| `quality`              | REAL              | No               | `float`            | Finite dimensionless section weighting metadata.            |
| `created_at`           | TEXT              | No               | `datetime`         | ISO timestamp with timezone, preserved instant.             |
| `gauge_shot_uuid`      | TEXT              | Yes              | `UUID`             | Gauge shot identity metadata; no correction applied.        |
| `gauge_neighbour_uuid` | TEXT              | Yes              | `UUID`             | Gauge neighbour identity metadata.                          |
| `reverse_parity`       | INTEGER           | No               | `bool`             | INTEGER 0 false, 1 true; other values rejected.             |
| `azimuth_north`        | TEXT              | Yes              | `NorthReference`   | TEXT magnetic, true, grid; NULL means no override recorded. |
| `azimuth_correction`   | REAL              | Yes              | `float`            | Degrees to add for true north; stored without applying.     |
| `azimuth_source`       | TEXT              | Yes              | `CorrectionSource` | TEXT unknown, file, igrf, manual.                           |
| `azimuth_epoch_year`   | INTEGER           | Yes              | `int`              | Geomagnetic model epoch year metadata.                      |

### `shots`

| Column           | Declared SQL type | SQL nullable     | Python type | Meaning / unit                                                    |
| ---------------- | ----------------- | ---------------- | ----------- | ----------------------------------------------------------------- |
| `id`             | INTEGER           | No (primary key) | `int`       | Database row identity; sections may be noncontiguous.             |
| `section_id`     | INTEGER           | No               | `int`       | References sections.id.                                           |
| `sequence_order` | INTEGER           | No               | `int`       | Zero-based position within section; contiguous.                   |
| `azimuth_in`     | REAL              | No               | `float`     | First forward bearing, degrees [0,360).                           |
| `azimuth_out`    | REAL              | No               | `float`     | Second forward bearing, degrees [0,360); not reciprocal.          |
| `length`         | REAL              | No               | `float`     | Slope length in metres, nonnegative.                              |
| `depth_in`       | REAL              | No               | `float`     | Start depth in metres, positive down.                             |
| `depth_out`      | REAL              | No               | `float`     | End depth in metres, positive down.                               |
| `pitch_in`       | REAL              | Yes              | `float`     | First pitch in degrees [-90,90], positive down.                   |
| `pitch_out`      | REAL              | Yes              | `float`     | Second pitch in degrees [-90,90], positive down.                  |
| `left_distance`  | REAL              | Yes              | `float`     | Passage dimension in metres, nonnegative; NULL differs from zero. |
| `right_distance` | REAL              | Yes              | `float`     | Passage dimension in metres, nonnegative; NULL differs from zero. |
| `up_distance`    | REAL              | Yes              | `float`     | Passage dimension in metres, nonnegative; NULL differs from zero. |
| `down_distance`  | REAL              | Yes              | `float`     | Passage dimension in metres, nonnegative; NULL differs from zero. |
| `comment`        | TEXT              | Yes              | `str`       | Text preserved verbatim; separate shot/station ownership.         |
| `kind`           | INTEGER           | No               | `ShotKind`  | INTEGER 0 normal, 1 jump, 2 reference.                            |
| `marker_index`   | INTEGER           | Yes              | `int`       | Physical marker index on cave line.                               |
| `temperature`    | REAL              | Yes              | `float`     | Water temperature in Celsius.                                     |
| `uuid`           | TEXT              | Yes              | `UUID`      | Persistent identity with section_id; never generated.             |

### `station_comments`

| Column          | Declared SQL type | SQL nullable | Python type | Meaning / unit                                            |
| --------------- | ----------------- | ------------ | ----------- | --------------------------------------------------------- |
| `section_id`    | INTEGER           | No           | `int`       | References sections.id.                                   |
| `station_index` | INTEGER           | No           | `int`       | Position 0 through shot count, inclusive.                 |
| `comment`       | TEXT              | No           | `str`       | Text preserved verbatim; separate shot/station ownership. |

### `project_settings`

| Column  | Declared SQL type | SQL nullable | Python type | Meaning / unit                                      |
| ------- | ----------------- | ------------ | ----------- | --------------------------------------------------- |
| `key`   | TEXT              | Yes          | `str`       | Only default_azimuth_reference is selected.         |
| `value` | TEXT              | No           | `JSON text` | Native AzimuthReference; mapped as described below. |

`project.next_closure_id` is closure allocator state and is intentionally
omitted. No section-comment column exists. Shot comments live in
`shots.comment`. Native `station_comments.comment` is declared NOT NULL; the
public comment model also permits None to preserve nulls in independently
produced schema-18 files.

## Relationships and identity

`shots.section_id` and `station_comments.section_id` reference `sections.id`.
The native database declares cascading foreign keys, unique
`(section_id, sequence_order)` and a station-comment primary key of
`(section_id, station_index)`. Validation enforces these relationships even if
SQLite constraints are absent or disabled. All section IDs and shot row IDs must
be unique; non-null shot UUIDs must be unique within each section.

`SurveyShot.id` is the SQLite row ID. The application constructs a different
runtime ID from section and sequence when opening a project; that transient ID
is not exposed here. `(section_id, uuid)` is persistent identity when UUID
exists. NULL UUIDs stay None. Gauge UUIDs remain metadata; they do not trigger
station merges or geometry changes.

A section with N shots has N+1 station positions. Shot i connects station i to
station i+1. Comments at shared stations are stored once, separately from both
adjacent shots. An empty section can have a station-0 comment. Names and
surveyor text are not identifiers. Sections sort by ID and shots by zero-based
sequence.

Shot kinds are `0 = normal` (permanent leg), `1 = jump` (swum shortcut), and
`2 = reference` (non-swimmable survey tie). These labels do not cause filtering;
all shot kinds remain in the exported survey.

## Bearing metadata

Sections retain the four nullable `azimuth_*` columns independently, including
partial metadata. NULL north means no section override was recorded. The project
setting key `default_azimuth_reference` contains native JSON with `north`,
`correction`, and `source`. Other settings are never selected. Missing table or
key yields None. A malformed value or duplicate relevant key fails validation.

Native source JSON maps to the public flat model as follows:

| Native project source               | Public source | Public epoch_year |
| ----------------------------------- | ------------- | ----------------- |
| `"unknown"`                         | `"unknown"`   | None              |
| `"file_declared"`                   | `"file"`      | None              |
| `"manual"`                          | `"manual"`    | None              |
| `{"igrf_auto":{"epoch_year":2026}}` | `"igrf"`      | 2026              |

`north` is magnetic, true, or grid. Correction is degrees to add to a stored
bearing to obtain true north (east declination is positive; grid correction
includes convergence). The native application normally stores zero for true
north. The reader retains the recorded number without normalizing it or applying
it, and does not resolve section overrides against the project default.

## Geographic metadata

`Survey.zero_datums` and `Survey.station_merges` are tuples sorted by row ID.
The optional ordinary tables preserve the following native fields:

| Table            | Columns                                                                                           |
| ---------------- | ------------------------------------------------------------------------------------------------- |
| `zero_datums`    | `id`, `section_id`, `station_index`, `latitude`, `longitude`, `depth_reference`                   |
| `station_merges` | `id`, `station_a_section`, `station_a_index`, `station_b_section`, `station_b_index`, `merged_at` |

IDs and station references are strict integers. Datum coordinates and depth
references are finite; latitude is bounded by ±90 and longitude by ±180. Merge
timestamps require a timezone. Row IDs are unique within each collection, and
datum `(section_id, station_index)` pairs are unique. Both merge endpoints and
datum stations must reference an existing section at station zero through its
shot count, including empty sections at station zero. Metadata reading neither
applies merges nor calculates coordinates. Native fixture regression tests
compare every supported column directly to the unchanged database.

## Scope and replacement boundary

JSON is the supported survey data, not a full project backup. Measurements stay
as stored; null, empty text, whitespace, Unicode and zero remain distinct. The
reader never infers pitch, averages bearings, repairs inconsistent depth,
applies corrections, or modifies native files. Geometry calculation,
connectivity correction, closures, settings other than bearing reference,
history, and native writing are outside the reader. Datums and merges are
preserved as metadata for adapters such as OpenSpeleo. Only schema 18 is
supported.

The inherited implementation was an XML/TML parser: parser, shot, section and
enum modules were replaced; `key_map.py`, `type_utils.py`, lazy XML access,
native XML writing, section statistics and the `correct` action were removed.
Obsolete TML/TMLU fixtures and generated JSON exports and their key-map and
statistics tests were removed; reader, section, and enum tests now exercise the
native API, with independent property tests for each Pydantic model. XML
dependencies (`defusedxml`, `dicttoxml2`, `xmltodict`), `orjson`, and legacy
test helpers (`parameterized`, `pytest-env`, `pytest-runner`, `pytest-ordering`)
are no longer dependencies. The native example, Flit package layout, CLI name,
version metadata, license and Python CI matrix are retained.
