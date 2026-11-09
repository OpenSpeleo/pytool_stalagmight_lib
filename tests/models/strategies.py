"""Valid native model inputs, independent of database parsing."""

from datetime import UTC

from hypothesis import strategies as st

from stalagmight_lib import AzimuthReference
from stalagmight_lib import ProjectMetadata
from stalagmight_lib import StationComment
from stalagmight_lib import StationMerge
from stalagmight_lib import SurveySection
from stalagmight_lib import SurveyShot
from stalagmight_lib import ZeroDatum
from stalagmight_lib.enums import CorrectionSource
from stalagmight_lib.enums import NorthReference
from stalagmight_lib.enums import ShotKind
from stalagmight_lib.enums import SurveyDirection

text = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=80)
nullable_text = st.one_of(st.none(), text)
finite = st.floats(allow_nan=False, allow_infinity=False)
nonnegative = st.floats(min_value=0, allow_nan=False, allow_infinity=False)
integers = st.integers(min_value=-1000000, max_value=1000000)
indices = st.integers(min_value=0, max_value=1000000)
timestamps = st.datetimes(timezones=st.just(UTC))
nullable_uuid = st.one_of(st.none(), st.uuids())

references = st.builds(
    AzimuthReference,
    north=st.sampled_from(NorthReference),
    correction=finite,
    source=st.sampled_from(CorrectionSource),
    epoch_year=st.one_of(st.none(), integers),
)
projects = st.builds(
    ProjectMetadata,
    id=integers,
    name=text,
    location=nullable_text,
    created_at=timestamps,
    modified_at=timestamps,
    default_azimuth_reference=st.one_of(st.none(), references),
)
comments = st.builds(
    StationComment,
    section_id=integers,
    station_index=indices,
    comment=nullable_text,
)
datums = st.builds(
    ZeroDatum,
    id=integers,
    section_id=integers,
    station_index=indices,
    latitude=st.floats(min_value=-90, max_value=90),
    longitude=st.floats(min_value=-180, max_value=180),
    depth_reference=finite,
)
merges = st.builds(
    StationMerge,
    id=integers,
    station_a_section=integers,
    station_a_index=indices,
    station_b_section=integers,
    station_b_index=indices,
    merged_at=timestamps,
)
shots = st.builds(
    SurveyShot,
    id=integers,
    section_id=integers,
    sequence_order=indices,
    uuid=nullable_uuid,
    azimuth_in=st.floats(min_value=0, max_value=360, exclude_max=True),
    azimuth_out=st.floats(min_value=0, max_value=360, exclude_max=True),
    length=nonnegative,
    depth_in=finite,
    depth_out=finite,
    pitch_in=st.one_of(st.none(), st.floats(min_value=-90, max_value=90)),
    pitch_out=st.one_of(st.none(), st.floats(min_value=-90, max_value=90)),
    left_distance=st.one_of(st.none(), nonnegative),
    right_distance=st.one_of(st.none(), nonnegative),
    up_distance=st.one_of(st.none(), nonnegative),
    down_distance=st.one_of(st.none(), nonnegative),
    comment=nullable_text,
    kind=st.sampled_from(ShotKind),
    marker_index=st.one_of(st.none(), integers),
    temperature=st.one_of(st.none(), finite),
)


@st.composite
def sections(draw, *, section_id=None):
    section_id = draw(integers) if section_id is None else section_id
    legs = draw(st.lists(shots, max_size=4))
    normalized = tuple(
        SurveyShot.model_validate(
            {
                **shot.model_dump(),
                "id": section_id * 10 + index,
                "section_id": section_id,
                "sequence_order": index,
                # UUID uniqueness is a separate constraint; nulls are always valid.
                "uuid": None,
            }
        )
        for index, shot in enumerate(legs)
    )
    station_comments = tuple(
        StationComment(
            section_id=section_id, station_index=index, comment=draw(nullable_text)
        )
        for index in draw(st.sets(st.integers(min_value=0, max_value=len(legs))))
    )
    return SurveySection(
        id=section_id,
        name=draw(nullable_text),
        surveyor=draw(nullable_text),
        date=draw(st.one_of(st.none(), st.dates())),
        created_at=draw(timestamps),
        color=draw(text),
        direction=draw(st.sampled_from(SurveyDirection)),
        quality=draw(finite),
        reverse_parity=draw(st.booleans()),
        gauge_shot_uuid=draw(nullable_uuid),
        gauge_neighbour_uuid=draw(nullable_uuid),
        azimuth_north=draw(st.one_of(st.none(), st.sampled_from(NorthReference))),
        azimuth_correction=draw(st.one_of(st.none(), finite)),
        azimuth_source=draw(st.one_of(st.none(), st.sampled_from(CorrectionSource))),
        azimuth_epoch_year=draw(st.one_of(st.none(), integers)),
        shots=normalized,
        station_comments=station_comments,
    )
