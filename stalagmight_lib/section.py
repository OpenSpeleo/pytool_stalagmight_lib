"""Sections retain their native metadata and positional station comments."""

from typing import Annotated

from pydantic import Field
from pydantic import model_validator

from stalagmight_lib._model import DateValue
from stalagmight_lib._model import SurveyModel
from stalagmight_lib._model import Timestamp
from stalagmight_lib._model import UUIDValue
from stalagmight_lib._model import enum_decoder
from stalagmight_lib.enums import CorrectionSource
from stalagmight_lib.enums import NorthReference
from stalagmight_lib.enums import SurveyDirection
from stalagmight_lib.shot import SurveyShot

NorthValue = Annotated[NorthReference, enum_decoder(NorthReference, str)]
SourceValue = Annotated[CorrectionSource, enum_decoder(CorrectionSource, str)]


class StationComment(SurveyModel):
    section_id: int
    station_index: Annotated[int, Field(ge=0)]
    comment: str | None


class SurveySection(SurveyModel):
    id: int
    name: str | None
    surveyor: str | None
    date: DateValue | None
    created_at: Timestamp
    color: str
    direction: Annotated[SurveyDirection, enum_decoder(SurveyDirection, str)]
    quality: float
    reverse_parity: bool
    gauge_shot_uuid: UUIDValue | None
    gauge_neighbour_uuid: UUIDValue | None
    azimuth_north: NorthValue | None
    azimuth_correction: float | None
    azimuth_source: SourceValue | None
    azimuth_epoch_year: int | None
    shots: tuple[SurveyShot, ...] = ()
    station_comments: tuple[StationComment, ...] = ()

    @model_validator(mode="after")
    def validate_relationships(self):
        ids, uuids = set(), set()
        for index, shot in enumerate(self.shots):
            context = (
                f"shots row {shot.id} section {self.id} sequence {shot.sequence_order}"
            )
            if shot.section_id != self.id:
                raise ValueError(f"{context}: section_id does not match section")
            if shot.sequence_order != index:
                raise ValueError(
                    f"{context}: sequence_order must be contiguous from zero"
                )
            if shot.id in ids:
                raise ValueError(f"{context}: duplicate id")
            if shot.uuid is not None and shot.uuid in uuids:
                raise ValueError(f"{context}: duplicate uuid {shot.uuid}")
            ids.add(shot.id)
            if shot.uuid is not None:
                uuids.add(shot.uuid)
        return self

    @model_validator(mode="after")
    def validate_station_comments(self):
        stations = set()
        for comment in self.station_comments:
            context = (
                f"station_comments section {self.id} station {comment.station_index}"
            )
            if comment.section_id != self.id:
                raise ValueError(f"{context}: section_id does not match section")
            if (comment.station_index & 0x7FFFFFFF) > len(self.shots):
                raise ValueError(f"{context}: station_index exceeds shot count")
            if comment.station_index in stations:
                raise ValueError(f"{context}: duplicate station_index")
            stations.add(comment.station_index)
        return self

    def station_comment(self, index: int) -> str | None:
        for comment in self.station_comments:
            if comment.station_index == index:
                return comment.comment
        return None
