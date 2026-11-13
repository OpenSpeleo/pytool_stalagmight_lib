"""Complete supported survey data and project bearing metadata."""

from typing import Annotated
from typing import Literal

from pydantic import Field
from pydantic import model_validator

from stalagmight_lib._model import SurveyModel
from stalagmight_lib._model import Timestamp
from stalagmight_lib.graph import SHOT_START_INDEX_FLAG
from stalagmight_lib.graph import AzimuthReference
from stalagmight_lib.graph import LoopClosure
from stalagmight_lib.graph import SectionOffset
from stalagmight_lib.graph import ShotGraph
from stalagmight_lib.graph import ShotNumbering
from stalagmight_lib.graph import StationOffset
from stalagmight_lib.section import SurveySection
from stalagmight_lib.shot import SurveyShot


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
    schema_version: Literal[18, 19] = 18
    project: ProjectMetadata
    sections: tuple[SurveySection, ...] = ()

    zero_datums: tuple[ZeroDatum, ...] = ()
    station_merges: tuple[StationMerge, ...] = ()

    loop_closures: tuple[LoopClosure, ...] = ()
    shot_numbering: ShotNumbering | None = None
    shot_graph: ShotGraph | None = None
    section_offsets: tuple[SectionOffset, ...] = ()
    station_offsets: tuple[StationOffset, ...] = ()

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
                    if not self.valid_station_index(section_id, index):
                        raise ValueError(f"{context}: station_index exceeds shot count")
        return self

    def valid_station_index(self, section_id: int, index: int) -> bool:
        section = next((s for s in self.sections if s.id == section_id), None)
        if section is None:
            return False
        if index & SHOT_START_INDEX_FLAG:
            return (
                self.schema_version == 19
                and self.shot_graph is not None
                and self.shot_graph.explicit
                and 0 < (index & ~SHOT_START_INDEX_FLAG) < len(section.shots)
            )
        return 0 <= index <= len(section.shots)

    def live_numbers(self) -> dict[tuple[int, int], int]:
        if self.shot_numbering is None:
            raise ValueError("native permanent numbering is missing")
        identities = {
            entry.identity: entry.number for entry in self.shot_numbering.identities
        }
        result = {}
        for section in self.sections:
            for shot in section.shots:
                identity = (
                    f"{section.id}:{shot.uuid}"
                    if shot.uuid is not None
                    else f"{section.id}:legacy:{shot.sequence_order}"
                )
                if identity not in identities:
                    raise ValueError(f"shot row {shot.id}: missing permanent number")
                result[section.id, shot.sequence_order] = identities[identity]
        if len(set(result.values())) != len(result):
            raise ValueError("duplicate live permanent number")
        return result

    def _validate_numbering(self):
        if self.schema_version == 19:
            if self.shot_graph is None or self.shot_numbering is None:
                raise ValueError("schema 19 requires shot_graph and shot_numbering")
            numbers = self.live_numbers()
            live = set(numbers.values())
            origins = {entry.number: entry.parent for entry in self.shot_graph.origins}
            if self.shot_graph.explicit:
                if not self.shot_graph.initialized:
                    raise ValueError("explicit graph is not initialized")
                for number in live:
                    if number not in origins:
                        raise ValueError(f"shot {number}: missing explicit origin")
                    parent, seen = origins[number], set()
                    while parent is not None and parent not in live:
                        if parent in seen or parent not in origins:
                            raise ValueError(f"shot {number}: broken retired ancestry")
                        seen.add(parent)
                        parent = origins[parent]

    @model_validator(mode="after")
    def validate_native_graph(self):
        self._validate_numbering()
        for table, records in (
            ("loop_closures", self.loop_closures),
            ("section_offsets", self.section_offsets),
            ("station_offsets", self.station_offsets),
        ):
            keys = set()
            for record in records:
                if isinstance(record, LoopClosure):
                    key = record.id
                    refs = (
                        (record.station_a_section, record.station_a_index),
                        (record.station_b_section, record.station_b_index),
                    )
                else:
                    key = (
                        (record.section_id, record.station_index)
                        if isinstance(record, StationOffset)
                        else record.section_id
                    )
                    refs = (
                        ((record.section_id, record.station_index),)
                        if isinstance(record, StationOffset)
                        else ((record.section_id, 0),)
                    )
                if key in keys:
                    raise ValueError(f"{table}: duplicate identity")
                keys.add(key)
                if any(not self.valid_station_index(s, i) for s, i in refs):
                    raise ValueError(f"{table}: invalid station reference")
        for section in self.sections:
            for comment in section.station_comments:
                if not self.valid_station_index(section.id, comment.station_index):
                    raise ValueError("station_comments: invalid station reference")
        return self
