"""Frozen native graph evidence; no migrations, repair, or layout cycle cuts."""

from typing import Annotated

from pydantic import Field
from pydantic import model_validator

from stalagmight_lib._model import SurveyModel
from stalagmight_lib.section import NorthValue
from stalagmight_lib.section import SourceValue

Number = Annotated[int, Field(gt=0, le=0xFFFFFFFF)]
SHOT_START_INDEX_FLAG = 0x80000000


class AzimuthReference(SurveyModel):
    north: NorthValue
    correction: float
    source: SourceValue
    epoch_year: int | None = None


class NumberIdentity(SurveyModel):
    identity: str
    number: Number


class ShotNumbering(SurveyModel):
    next: Annotated[int, Field(gt=0, le=0x100000000)]
    identities: tuple[NumberIdentity, ...] = ()

    @model_validator(mode="after")
    def unique_identities(self):
        if len({entry.identity for entry in self.identities}) != len(self.identities):
            raise ValueError("duplicate numbering identity")
        return self


class ShotOrigin(SurveyModel):
    number: Number
    parent: Number | None


class RootPosition(SurveyModel):
    number: Number
    value: tuple[float, float]


class AzimuthOverride(SurveyModel):
    number: Number
    reference: AzimuthReference


class GeometryLock(SurveyModel):
    number: Number
    locked: bool


class ShotGraph(SurveyModel):
    initialized: bool = False
    explicit: bool = False
    origins: tuple[ShotOrigin, ...] = ()
    root_positions: tuple[RootPosition, ...] = ()
    azimuth_overrides: tuple[AzimuthOverride, ...] = ()
    geometry_locks: tuple[GeometryLock, ...] = ()

    @model_validator(mode="after")
    def unique_entries(self):
        for entries in (
            self.origins,
            self.root_positions,
            self.azimuth_overrides,
            self.geometry_locks,
        ):
            if len({entry.number for entry in entries}) != len(entries):
                raise ValueError("duplicate shot graph key")
        return self


class LoopClosure(SurveyModel):
    id: int
    station_a_section: int
    station_a_index: Annotated[int, Field(ge=0, le=0xFFFFFFFF)]
    station_b_section: int
    station_b_index: Annotated[int, Field(ge=0, le=0xFFFFFFFF)]
    path_length: float
    misclosure_distance: float
    error_percentage: float
    horizontal_misclosure: float | None
    vertical_misclosure: float | None
    closure_id: int | None = None
    strategy: str | None = None
    is_aligned: bool | None = None


class SectionOffset(SurveyModel):
    section_id: int
    offset_x: float
    offset_y: float


class StationOffset(SectionOffset):
    station_index: Annotated[int, Field(ge=0, le=0xFFFFFFFF)]
    offset_z: float
