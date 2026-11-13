"""Native protocol fixtures independently assembled without application migrations."""

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from stalagmight_lib import AzimuthReference
from stalagmight_lib import DataValidationError
from stalagmight_lib import Survey
from stalagmight_lib import read_stalx
from stalagmight_lib.graph import AzimuthOverride
from stalagmight_lib.graph import GeometryLock
from stalagmight_lib.graph import LoopClosure
from stalagmight_lib.graph import NumberIdentity
from stalagmight_lib.graph import RootPosition
from stalagmight_lib.graph import SectionOffset
from stalagmight_lib.graph import ShotGraph
from stalagmight_lib.graph import ShotNumbering
from stalagmight_lib.graph import ShotOrigin
from stalagmight_lib.graph import StationOffset
from tests.conftest import execute
from tests.models.test_models import assert_model_contract


def schema19(database, *, origins=None, identities=None):
    execute(database, "PRAGMA user_version=19")
    execute(database, "UPDATE project SET schema_version=19")
    numbering = {"next": 4, "identities": identities or {"42:legacy:0": 1}}
    graph = {
        "initialized": True,
        "explicit": True,
        "origins": origins or {"1": None},
        "root_positions": {"1": [123.0, 456.0]},
        "geometry_locks": {"1": True},
    }
    for key, value in (("shot_numbering", numbering), ("shot_graph", graph)):
        execute(
            database,
            "INSERT INTO project_settings VALUES (?,?)",
            (key, json.dumps(value)),
        )


def test_schema19_preserves_frozen_metadata(database):
    schema19(
        database,
        origins={"1": 2, "2": None},
        identities={"42:legacy:0": 1, "retired": 2},
    )
    original = database.read_bytes()
    survey = read_stalx(database)
    assert survey.schema_version == 19
    assert survey.live_numbers() == {(42, 0): 1}
    assert survey.shot_graph.origins[0].parent == 2
    assert survey.shot_graph.geometry_locks[0].locked
    assert survey.shot_graph.root_positions[0].value == (123.0, 456.0)
    assert database.read_bytes() == original
    assert Survey.model_validate_json(survey.model_dump_json()) == survey


@pytest.mark.parametrize("kind", ["missing", "broken", "retired_cycle", "duplicate"])
def test_rejects_malformed_schema19(database, kind):
    if kind == "missing":
        schema19(database, identities={"other": 1})
    elif kind == "broken":
        schema19(database, origins={"1": 3})
    elif kind == "retired_cycle":
        schema19(database, origins={"1": 2, "2": 3, "3": 2})
    else:
        schema19(database)
        execute(database, "INSERT INTO project_settings VALUES ('shot_graph', '{}')")
    with pytest.raises(DataValidationError):
        read_stalx(database)


def test_live_origin_cycles_and_interior_starts(database):
    execute(
        database,
        "INSERT INTO shots SELECT 100, section_id, 1, azimuth_in, azimuth_out, "
        "length, depth_in, depth_out, pitch_in, pitch_out, left_distance, "
        "right_distance, up_distance, down_distance, comment, kind, marker_index, "
        "temperature, NULL FROM shots",
    )
    schema19(
        database,
        origins={"1": 2, "2": 1},
        identities={"42:legacy:0": 1, "42:legacy:1": 2},
    )
    execute(
        database,
        "INSERT INTO station_comments VALUES (42, ?, 'interior start')",
        (0x80000001,),
    )
    survey = read_stalx(database)
    assert survey.valid_station_index(42, 0x80000001)
    assert not survey.valid_station_index(42, 0x80000002)
    assert len(survey.shot_graph.origins) == 2


@given(st.integers(min_value=1, max_value=0xFFFFFFFF))
def test_all_graph_models_direct_contract(number):
    reference = AzimuthReference(north="grid", correction=0.0, source="file")
    models = [
        NumberIdentity(identity="retained", number=number),
        ShotNumbering(
            next=0x100000000,
            identities=(NumberIdentity(identity="retained", number=number),),
        ),
        ShotOrigin(number=number, parent=None),
        RootPosition(number=number, value=(1.0, 2.0)),
        AzimuthOverride(number=number, reference=reference),
        GeometryLock(number=number, locked=False),
        ShotGraph(origins=(ShotOrigin(number=number, parent=None),)),
        SectionOffset(section_id=42, offset_x=1.0, offset_y=2.0),
        StationOffset(
            section_id=42, station_index=0, offset_x=1.0, offset_y=2.0, offset_z=3.0
        ),
        LoopClosure(
            id=1,
            station_a_section=42,
            station_a_index=0,
            station_b_section=42,
            station_b_index=1,
            path_length=1.0,
            misclosure_distance=0.0,
            error_percentage=0.0,
            horizontal_misclosure=None,
            vertical_misclosure=None,
        ),
    ]
    for model in models:
        assert_model_contract(model)
    with pytest.raises(ValidationError):
        ShotGraph(origins=(ShotOrigin(number=number, parent=None),) * 2)
