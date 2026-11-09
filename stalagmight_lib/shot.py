"""Stored shot readings; no corrections or geometry are applied."""

from typing import Annotated

from pydantic import Field

from stalagmight_lib._model import Azimuth
from stalagmight_lib._model import Nonnegative
from stalagmight_lib._model import Pitch
from stalagmight_lib._model import SurveyModel
from stalagmight_lib._model import UUIDValue
from stalagmight_lib._model import enum_decoder
from stalagmight_lib.enums import ShotKind


class SurveyShot(SurveyModel):
    id: int
    section_id: int
    sequence_order: Annotated[int, Field(ge=0)]
    uuid: UUIDValue | None
    azimuth_in: Azimuth
    azimuth_out: Azimuth
    length: Nonnegative
    depth_in: float
    depth_out: float
    pitch_in: Pitch | None
    pitch_out: Pitch | None
    left_distance: Nonnegative | None
    right_distance: Nonnegative | None
    up_distance: Nonnegative | None
    down_distance: Nonnegative | None
    comment: str | None
    kind: Annotated[ShotKind, enum_decoder(ShotKind, int)]
    marker_index: int | None
    temperature: float | None

    @property
    def start_station_index(self) -> int:
        return self.sequence_order

    @property
    def end_station_index(self) -> int:
        return self.sequence_order + 1
