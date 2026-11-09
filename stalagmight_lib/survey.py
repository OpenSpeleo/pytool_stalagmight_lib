"""Complete supported survey data and project bearing metadata."""

from typing import Annotated
from typing import Literal

from pydantic import Field
from pydantic import model_validator

from stalagmight_lib._model import SurveyModel
from stalagmight_lib._model import Timestamp
from stalagmight_lib.section import NorthValue
from stalagmight_lib.section import SourceValue
from stalagmight_lib.section import SurveySection
from stalagmight_lib.shot import SurveyShot


class AzimuthReference(SurveyModel):
    north: NorthValue
    correction: float
    source: SourceValue
    epoch_year: int | None = None


class ProjectMetadata(SurveyModel):
    id: int
    name: str
    location: str | None
    created_at: Timestamp
    modified_at: Timestamp
    default_azimuth_reference: AzimuthReference | None = None


class ZeroDatum(SurveyModel):
    id: int
    section_id: int
    station_index: Annotated[int, Field(ge=0)]
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    depth_reference: float


class StationMerge(SurveyModel):
    id: int
    station_a_section: int
    station_a_index: Annotated[int, Field(ge=0)]
    station_b_section: int
    station_b_index: Annotated[int, Field(ge=0)]
    merged_at: Timestamp


class Survey(SurveyModel):
    schema_version: Literal[18] = 18
    project: ProjectMetadata
    sections: tuple[SurveySection, ...] = ()

    zero_datums: tuple[ZeroDatum, ...] = ()
    station_merges: tuple[StationMerge, ...] = ()

    @property
    def shots(self) -> tuple[SurveyShot, ...]:
        return tuple(shot for section in self.sections for shot in section.shots)

    @model_validator(mode="after")
    def validate_ids(self):
        section_ids, shot_ids = set(), set()
        for section in self.sections:
            if section.id in section_ids:
                raise ValueError(f"sections row {section.id}: duplicate id")
            section_ids.add(section.id)
            for shot in section.shots:
                if shot.id in shot_ids:
                    raise ValueError(f"shots row {shot.id}: duplicate id")
                shot_ids.add(shot.id)
        return self

    @model_validator(mode="after")
    def validate_geographic_metadata(self):
        sections = {section.id: section for section in self.sections}
        datum_stations = set()
        for table, records in (
            ("zero_datums", self.zero_datums),
            ("station_merges", self.station_merges),
        ):
            ids = set()
            for record in records:
                context = f"{table} row {record.id}"
                if record.id in ids:
                    raise ValueError(f"{context}: duplicate id")
                ids.add(record.id)
                if isinstance(record, ZeroDatum):
                    references = [(record.section_id, record.station_index)]
                    station = references[0]
                    if station in datum_stations:
                        raise ValueError(f"{context}: duplicate datum station")
                    datum_stations.add(station)
                else:
                    references = [
                        (record.station_a_section, record.station_a_index),
                        (record.station_b_section, record.station_b_index),
                    ]
                for section_id, index in references:
                    if section_id not in sections:
                        raise ValueError(f"{context}: orphan section {section_id}")
                    if index > len(sections[section_id].shots):
                        raise ValueError(f"{context}: station_index exceeds shot count")
        return self
