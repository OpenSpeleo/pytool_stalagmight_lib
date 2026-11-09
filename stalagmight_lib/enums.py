"""Stable schema-18 discriminants and metadata tokens."""

from enum import IntEnum
from enum import StrEnum


class ShotKind(IntEnum):
    NORMAL = 0
    JUMP = 1
    REFERENCE = 2


class SurveyDirection(StrEnum):
    IN = "in"
    OUT = "out"


class NorthReference(StrEnum):
    MAGNETIC = "magnetic"
    TRUE = "true"
    GRID = "grid"


class CorrectionSource(StrEnum):
    UNKNOWN = "unknown"
    FILE = "file"
    IGRF = "igrf"
    MANUAL = "manual"
