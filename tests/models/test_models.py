"""Each Pydantic class validates directly, without SQLite or a parser."""

import itertools
import json
from datetime import datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from stalagmight_lib import AzimuthReference
from stalagmight_lib import ProjectMetadata
from stalagmight_lib import StationComment
from stalagmight_lib import StationMerge
from stalagmight_lib import Survey
from stalagmight_lib import SurveySection
from stalagmight_lib import SurveyShot
from stalagmight_lib import ZeroDatum
from stalagmight_lib._model import SurveyModel
from tests.models import strategies as native


def assert_model_contract(model):
    cls = type(model)
    assert cls.model_validate(model.model_dump()) == model
    assert cls.model_validate_json(model.model_dump_json()) == model
    assert repr(model)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        cls.model_validate({**model.model_dump(), "unexpected_field": True})
    if cls.model_fields:
        field = next(iter(cls.model_fields))
        with pytest.raises(ValidationError, match="frozen_instance"):
            setattr(model, field, getattr(model, field))


@given(st.dictionaries(st.text(min_size=1), st.integers(), min_size=1))
def test_survey_model_base_rejects_extra_fields(values):
    assert SurveyModel.model_validate({}).model_dump() == {}
    with pytest.raises(ValidationError, match="extra_forbidden"):
        SurveyModel.model_validate(values)


@given(native.references)
def test_azimuth_reference(reference):
    assert isinstance(reference, AzimuthReference)
    assert_model_contract(reference)


@given(native.projects)
def test_project_metadata(project):
    assert isinstance(project, ProjectMetadata)
    assert_model_contract(project)


@given(native.comments)
def test_station_comment(comment):
    assert isinstance(comment, StationComment)
    assert_model_contract(comment)


@given(native.shots)
def test_survey_shot(shot):
    assert isinstance(shot, SurveyShot)
    assert_model_contract(shot)
    assert shot.start_station_index == shot.sequence_order
    assert shot.end_station_index == shot.sequence_order + 1
    raw = json.loads(shot.model_dump_json())
    assert "start_station_index" not in raw
    assert "end_station_index" not in raw
    # Geometry is deliberately not a native-model validation requirement.
    invalid_geometry = {
        **shot.model_dump(),
        "length": 0.0,
        "depth_in": 0.0,
        "depth_out": 1.0,
    }
    assert SurveyShot.model_validate(invalid_geometry).depth_out == 1.0


@given(native.sections())
def test_survey_section(section):
    assert isinstance(section, SurveySection)
    assert_model_contract(section)
    for comment in section.station_comments:
        assert section.station_comment(comment.station_index) == comment.comment
    assert section.station_comment(len(section.shots) + 1) is None


@given(native.datums)
def test_zero_datum(datum):
    assert isinstance(datum, ZeroDatum)
    assert_model_contract(datum)


@given(native.merges)
def test_station_merge(merge):
    assert isinstance(merge, StationMerge)
    assert_model_contract(merge)


@given(native.projects, st.data())
def test_survey(project, data):
    section_ids = data.draw(st.sets(native.integers, max_size=3))
    sections = tuple(
        data.draw(native.sections(section_id=index)) for index in sorted(section_ids)
    )
    datums = tuple(
        ZeroDatum(
            id=index,
            section_id=section.id,
            station_index=len(section.shots),
            latitude=0.0,
            longitude=0.0,
            depth_reference=0.0,
        )
        for index, section in enumerate(sections)
    )
    merges = tuple(
        StationMerge(
            id=index,
            station_a_section=a.id,
            station_a_index=0,
            station_b_section=b.id,
            station_b_index=len(b.shots),
            merged_at=data.draw(native.timestamps),
        )
        for index, (a, b) in enumerate(itertools.pairwise(sections))
    )
    survey = Survey(
        project=project, sections=sections, zero_datums=datums, station_merges=merges
    )
    assert_model_contract(survey)
    assert survey.shots == tuple(shot for section in sections for shot in section.shots)
    for collection in (
        survey.sections,
        survey.shots,
        survey.zero_datums,
        survey.station_merges,
    ):
        assert isinstance(collection, tuple)


@pytest.mark.parametrize(
    ("model", "strategy", "field"),
    [
        (ProjectMetadata, native.projects, "id"),
        (StationComment, native.comments, "station_index"),
        (SurveyShot, native.shots, "sequence_order"),
        (SurveySection, native.sections(), "id"),
        (ZeroDatum, native.datums, "station_index"),
        (StationMerge, native.merges, "station_a_index"),
    ],
)
@given(st.data(), st.one_of(st.booleans(), st.text(), st.floats()))
def test_integer_fields_reject_coercion(model, strategy, field, data, value):
    raw = data.draw(strategy).model_dump()
    raw[field] = value
    with pytest.raises(ValidationError):
        model.model_validate(raw)


@pytest.mark.parametrize(
    ("model", "strategy", "field"),
    [
        (AzimuthReference, native.references, "correction"),
        (SurveyShot, native.shots, "depth_in"),
        (SurveySection, native.sections(), "quality"),
        (ZeroDatum, native.datums, "depth_reference"),
    ],
)
@given(
    st.data(), st.sampled_from([float("nan"), float("inf"), -float("inf"), True, "0"])
)
def test_numeric_fields_reject_nonfinite_and_coercion(
    model, strategy, field, data, value
):
    raw = data.draw(strategy).model_dump()
    raw[field] = value
    with pytest.raises(ValidationError):
        model.model_validate(raw)


@pytest.mark.parametrize(
    ("model", "strategy", "field"),
    [
        (ProjectMetadata, native.projects, "created_at"),
        (SurveySection, native.sections(), "created_at"),
        (StationMerge, native.merges, "merged_at"),
    ],
)
@given(st.data(), st.datetimes())
def test_timestamps_require_timezone(model, strategy, field, data, naive):
    assert isinstance(naive, datetime)
    raw = data.draw(strategy).model_dump()
    raw[field] = naive
    with pytest.raises(ValidationError):
        model.model_validate(raw)


@pytest.mark.parametrize(
    ("model", "strategy", "field", "invalid"),
    [
        (
            SurveyShot,
            native.shots,
            "length",
            st.floats(max_value=-1e-100, allow_infinity=False),
        ),
        (
            SurveyShot,
            native.shots,
            "left_distance",
            st.floats(max_value=-1e-100, allow_infinity=False),
        ),
        (
            SurveyShot,
            native.shots,
            "azimuth_in",
            st.floats(min_value=360, allow_infinity=False),
        ),
        (
            SurveyShot,
            native.shots,
            "pitch_in",
            st.floats(min_value=91, allow_infinity=False),
        ),
        (
            SurveyShot,
            native.shots,
            "pitch_out",
            st.floats(max_value=-91, allow_infinity=False),
        ),
        (StationComment, native.comments, "station_index", st.integers(max_value=-1)),
        (
            ZeroDatum,
            native.datums,
            "latitude",
            st.floats(min_value=91, allow_infinity=False),
        ),
        (
            ZeroDatum,
            native.datums,
            "longitude",
            st.floats(max_value=-181, allow_infinity=False),
        ),
        (ZeroDatum, native.datums, "station_index", st.integers(max_value=-1)),
        (StationMerge, native.merges, "station_b_index", st.integers(max_value=-1)),
    ],
)
@given(st.data())
def test_model_field_bounds(model, strategy, field, invalid, data):
    raw = data.draw(strategy).model_dump()
    raw[field] = data.draw(invalid)
    with pytest.raises(ValidationError):
        model.model_validate(raw)


@pytest.mark.parametrize(
    "relationship",
    [
        "orphan_datum",
        "datum_station",
        "duplicate_datum_id",
        "duplicate_datum_station",
        "orphan_merge",
        "merge_station",
        "duplicate_merge_id",
    ],
)
@given(project=native.projects, section=native.sections(), timestamp=native.timestamps)
def test_survey_metadata_relationships(project, section, timestamp, relationship):
    datum = ZeroDatum(
        id=1,
        section_id=section.id,
        station_index=0,
        latitude=0.0,
        longitude=0.0,
        depth_reference=0.0,
    )
    merge = StationMerge(
        id=1,
        station_a_section=section.id,
        station_a_index=0,
        station_b_section=section.id,
        station_b_index=0,
        merged_at=timestamp,
    )
    datums, merges = [datum.model_dump()], [merge.model_dump()]
    if relationship == "orphan_datum":
        datums[0]["section_id"] += 1
    elif relationship == "datum_station":
        datums[0]["station_index"] = len(section.shots) + 1
    elif relationship == "duplicate_datum_id":
        datums.append(datums[0].copy())
    elif relationship == "duplicate_datum_station":
        datums.append({**datums[0], "id": 2})
    elif relationship == "orphan_merge":
        merges[0]["station_b_section"] += 1
    elif relationship == "merge_station":
        merges[0]["station_a_index"] = len(section.shots) + 1
    else:
        merges.append(merges[0].copy())
    with pytest.raises(ValidationError):
        Survey(
            project=project,
            sections=(section,),
            zero_datums=tuple(datums),
            station_merges=tuple(merges),
        )


@given(native.projects, native.shots, native.sections())
def test_survey_revalidates_nested_model_instances(project, shot, section):
    invalid_shot = SurveyShot.model_construct(**{**shot.model_dump(), "length": -1.0})
    invalid_section = SurveySection.model_construct(
        **{**section.model_dump(), "shots": (invalid_shot,)}
    )
    with pytest.raises(ValidationError):
        Survey(project=project, sections=(invalid_section,))
