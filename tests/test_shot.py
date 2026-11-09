"""Native shot identity and section relationships without database parsing."""

import pytest
from hypothesis import given
from pydantic import ValidationError

from stalagmight_lib import SurveySection
from stalagmight_lib import SurveyShot
from tests.models import strategies as native


@pytest.mark.parametrize(
    "relationship", ["membership", "sequence", "duplicate_id", "duplicate_uuid"]
)
@given(section=native.sections(), first=native.shots, second=native.shots)
def test_shot_relationships(section, first, second, relationship):
    first_data = {
        **first.model_dump(),
        "id": 1,
        "section_id": section.id,
        "sequence_order": 0,
        "uuid": None,
    }
    second_data = {
        **second.model_dump(),
        "id": 2,
        "section_id": section.id,
        "sequence_order": 1,
        "uuid": None,
    }
    if relationship == "membership":
        first_data["section_id"] += 1
    elif relationship == "sequence":
        second_data["sequence_order"] = 2
    elif relationship == "duplicate_id":
        second_data["id"] = 1
    else:
        first_data["uuid"] = second_data["uuid"] = (
            "f26c8521-2164-425d-b967-a4a4a874b69c"
        )
    shots = tuple(SurveyShot.model_validate(data) for data in (first_data, second_data))
    with pytest.raises(ValidationError):
        SurveySection.model_validate(
            {**section.model_dump(), "shots": shots, "station_comments": ()}
        )
