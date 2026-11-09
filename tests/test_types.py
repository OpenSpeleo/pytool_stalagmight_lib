"""Native enum tests replace enums belonging to the former XML format."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from stalagmight_lib import CorrectionSource
from stalagmight_lib import NorthReference
from stalagmight_lib import ShotKind
from stalagmight_lib import SurveyDirection


@pytest.mark.parametrize("enum", [CorrectionSource, NorthReference, SurveyDirection])
@given(st.text())
def test_string_enum_tokens(enum, token):
    known = {member.value for member in enum}
    if token in known:
        assert enum(token).value == token
    else:
        with pytest.raises(ValueError, match="is not a valid"):
            enum(token)


@given(st.integers())
def test_shot_kind_discriminants(token):
    known = {0: ShotKind.NORMAL, 1: ShotKind.JUMP, 2: ShotKind.REFERENCE}
    if token in known:
        assert ShotKind(token) is known[token]
    else:
        with pytest.raises(ValueError, match="is not a valid"):
            ShotKind(token)
