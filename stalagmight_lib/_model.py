"""Shared strict model configuration and explicit text decoders."""

from datetime import date
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime
from pydantic import BaseModel
from pydantic import BeforeValidator
from pydantic import ConfigDict
from pydantic import Field


class SurveyModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        revalidate_instances="always",
    )


def _uuid(value):
    return UUID(value) if isinstance(value, str) else value


def _date(value):
    return date.fromisoformat(value) if isinstance(value, str) else value


def _datetime(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def enum_decoder(enum, primitive):
    def decode(value):
        if type(value) is primitive:
            return enum(value)
        if isinstance(value, enum):
            return value
        raise ValueError(f"expected {enum.__name__} or {primitive.__name__} token")

    return BeforeValidator(decode)


UUIDValue = Annotated[UUID, BeforeValidator(_uuid)]
DateValue = Annotated[date, BeforeValidator(_date)]
Nonnegative = Annotated[float, Field(ge=0)]
Azimuth = Annotated[float, Field(ge=0, lt=360)]
Pitch = Annotated[float, Field(ge=-90, le=90)]
Timestamp = Annotated[AwareDatetime, BeforeValidator(_datetime)]
