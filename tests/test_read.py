"""Eager native parser facade regressions adapted from legacy reader tests."""

from pathlib import Path

import pytest

from stalagmight_lib import StalagmightParser
from stalagmight_lib import Survey
from stalagmight_lib import read_stalx


def test_parser_facade_and_native_json(database):
    before = database.read_bytes()
    mtime = database.stat().st_mtime_ns
    parser = StalagmightParser(str(database))
    assert parser.filepath == Path(database)
    assert parser.data == read_stalx(database)
    assert parser.sections == parser.data.sections
    assert parser.shots == parser.data.shots
    assert len(parser.shots) == sum(len(section.shots) for section in parser.sections)
    assert Survey.model_validate_json(parser.to_json()) == parser.data
    for shot in parser.shots:
        assert repr(shot)
    assert database.read_bytes() == before
    assert database.stat().st_mtime_ns == mtime


def test_parser_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        StalagmightParser(tmp_path / "missing.stalx")
