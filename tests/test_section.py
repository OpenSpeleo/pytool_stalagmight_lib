"""Section API regressions adapted from the former XML section tests."""

import pytest
from hypothesis import given
from pydantic import ValidationError

from stalagmight_lib import StationComment
from stalagmight_lib import SurveySection
from tests.models import strategies as native


@given(native.sections())
def test_section_repr_and_positional_comments(section):
    assert "SurveySection" in repr(section)
    for comment in section.station_comments:
        assert section.station_comment(comment.station_index) == comment.comment


@given(native.sections())
def test_empty_section_preserves_station_zero(section):
    comment = StationComment(section_id=section.id, station_index=0, comment="origin")
    empty = SurveySection.model_validate(
        {**section.model_dump(), "shots": (), "station_comments": (comment,)}
    )
    assert empty.shots == ()
    assert empty.station_comment(0) == "origin"
    assert empty.station_comment(1) is None


@pytest.mark.parametrize(
    "relationship", ["comment_membership", "duplicate_station", "out_of_bounds"]
)
@given(section=native.sections())
def test_invalid_section_comment_relationships(section, relationship):
    comment = {"section_id": section.id, "station_index": 0, "comment": None}
    comments = [comment]
    if relationship == "comment_membership":
        comment["section_id"] += 1
    elif relationship == "out_of_bounds":
        comment["station_index"] = len(section.shots) + 1
    else:
        comments.append(comment.copy())
    with pytest.raises(ValidationError):
        SurveySection.model_validate(
            {**section.model_dump(), "station_comments": tuple(comments)}
        )
