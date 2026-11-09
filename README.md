# stalagmight_lib

Read native StalagMight `.stalx` surveys into immutable Pydantic v2 models.
Python support is defined in `pyproject.toml` and the CI matrix. **Schema 18 is
the only supported file version.**

```bash
pip install stalagmight_lib
```

```python
from stalagmight_lib import Survey, read_stalx

survey = read_stalx("survey.stalx")
for section in survey.sections:
    print(section.id, section.name)
    print(section.station_comment(0))
    for shot in section.shots:
        print(shot.length, shot.comment)
        print(shot.start_station_index, shot.end_station_index)

json_text = survey.model_dump_json(indent=2)
restored = Survey.model_validate_json(json_text)
assert restored == survey
schema = Survey.model_json_schema()
```

`survey.shots` provides a tuple of all shots, ordered by section ID then
sequence. `StalagMightParser(filepath)` eagerly reads the same survey and
exposes `filepath`, `data`, `sections`, `shots`, and `to_json()`.

Shot comments belong to individual shots. Station comments remain separate in
`section.station_comments`; they are positional within a section, with station 0
at the beginning and station N after N shots. Unicode, whitespace, empty
strings, and SQL nulls are preserved. Missing measurements remain `None`; zero
stays zero. Measurements remain as stored, in metres, degrees, and Celsius.
Bearing reference metadata is retained without applying corrections.

```bash
stalagmight convert --input_file survey.stalx --output_file survey.json --format json
```

Existing output files require `--overwrite`. Input/output aliases, including
symlinks and hardlinks, are rejected. Failures are reported on stderr with a
nonzero exit code.

```python
from stalagmight_lib import StalagMightError, read_stalx

try:
    survey = read_stalx("survey.stalx")
except StalagMightError as error:
    print(f"Invalid or unsupported survey: {error}")
except OSError as error:
    print(f"Cannot access file: {error}")
```

Reading uses SQLite read-only mode and does not modify the source file. JSON
represents the supported survey data, **not a complete project backup**.
Geometry, connectivity, station merges, closures, datums, application settings,
history, native file writing, and correction commands are outside v1. Only the
project setting needed for the default bearing reference is read.

See the [format reference](docs/format.md) for every stored field and the
[API reference](docs/api.md) for validation and exception details.

## Development

```bash
uv sync --frozen --all-extras --dev
uv run pytest
uv run prek run --all-files
uv run flit build
```

The pytest suite uses the unchanged native fixture and temporary synthetic
SQLite files. CI runs the suite on the configured supported Python matrix. Prek
owns formatting and linting; do not install Git hooks. Keep standalone
dependencies and `uv.lock` authoritative. After changing dependencies, run
`uv lock` here.

## Geographic metadata and OpenSpeleo

`Survey.zero_datums` and `Survey.station_merges` are immutable tuples of
`ZeroDatum` and `StationMerge`. They preserve all native columns, including
datum station indices and depth references, and timezone-aware merge timestamps.
Optional absent tables produce empty tuples. The reader validates identities,
coordinate bounds, and station references (zero through the section shot count),
but does not apply merges or calculate geometry.

For maps, use the OpenSpeleo adapter and its shared exporter:

```python
from openspeleo_lib.interfaces import StalagMightInterface
from openspeleo_lib.geojson import survey_to_geojson

survey = StalagMightInterface.from_file("survey.stalx")
geojson = survey_to_geojson(survey)
```

```sh
openspeleo convert -i survey.stalx -o survey.geojson -f geojson --beautify
```

The pipeline is native reader → adapter → common survey → shared GeoJSON
exporter. `stalagmight convert` continues to export native-model JSON;
`openspeleo convert -f json` exports the normalized common model.

The adapter uses a deterministic section spanning forest rooted at the lowest-ID
datum in each connected component, or the lowest section ID without a datum. It
attaches sections at the actual merged stations, including intermediate and
final stations, and directs shots outward from those attachments. Reversal swaps
depths and left/right, rotates the bearing 180 degrees, and reverses
inclination. Native models remain unchanged. Additional merges are retained as
native metadata and reported without closure adjustment.

Export graph IDs are deterministic nonnegative IDs, separate from native row
IDs. The first occurrence of a valid v4 shot UUID supplies the optional feature
ID; unsupported and repeated UUIDs are omitted without replacements. Normal
shots produce features; jump and reference shots participate in positioning as
hidden VIRTUAL shots. Bearings use `azimuth_in` and recorded section correction
when section north metadata exists (null correction means zero), otherwise the
project correction, otherwise zero. No IGRF calculation is performed.

Each shot's own start depth controls its horizontal projection, allowing
recorded depth discontinuities. An individual shot shorter than its depth change
fails conversion with its native row, section, and sequence identity. The
unchanged example deliberately exercises this failure at shot 282. Failed
conversion leaves output untouched, and source/output aliases are refused.

GeoJSON retains OpenSpeleo's FeatureCollection, Point/LineString geometry,
precision, depth conversion, section names, color normalization, and filtering.
Native-only metadata, including positional station comments, does not become
feature properties. Zero latitude/longitude is valid. Explicit anchors use the
shared 500-metre consistency check; unanchored components are filtered, and a
survey without any anchor raises `NoKnownAnchorError`. Section offsets, station
moves, native adjusted maps, and loop-closure adjustments are not reproduced.

Each Pydantic model has independent Hypothesis property tests for its
validation, immutability, and JSON round-trips. Parser regressions separately
exercise SQLite schemas and relationships. Hypothesis is included in the package
test extra.
