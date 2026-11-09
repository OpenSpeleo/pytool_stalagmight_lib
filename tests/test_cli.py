import json
import shutil
import subprocess
from pathlib import Path

import pytest

from stalagmight_lib import Survey
from stalagmight_lib import read_stalx


def cli(*args):
    executable = shutil.which("stalagmight")
    assert executable is not None
    return subprocess.run(  # noqa: S603 - exercise installed entry point
        [executable, *map(str, args)], capture_output=True, text=True, check=False
    )


def arguments(database, output):
    return [
        "convert",
        "--input_file",
        database,
        "--output_file",
        output,
        "--format",
        "json",
    ]


def test_help_and_version():
    for args in [("--help",), ("--version",), ("convert", "--help")]:
        result = cli(*args)
        assert result.returncode == 0
        assert result.stdout
    assert cli("correct").returncode != 0


def test_export_and_overwrite(database, tmp_path):
    output = tmp_path / "survey.json"
    args = arguments(database, output)
    assert cli(*args).returncode == 0
    assert Survey.model_validate_json(output.read_text()) == read_stalx(database)
    output.write_text("retain this")
    result = cli(*args)
    assert result.returncode != 0
    assert "--overwrite" in result.stderr
    assert output.read_text() == "retain this"
    assert cli(*args, "--overwrite").returncode == 0
    assert json.loads(output.read_text())["schema_version"] == 18


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_source_alias(database, tmp_path, alias):
    before = database.read_bytes()
    output = database if alias == "same" else tmp_path / "output.json"
    if alias == "symlink":
        output.symlink_to(database)
    elif alias == "hardlink":
        output.hardlink_to(database)
    result = cli(*arguments(database, output), "--overwrite")
    assert result.returncode != 0
    assert "input file" in result.stderr
    assert database.read_bytes() == before


def test_failure(tmp_path):
    output = tmp_path / "output.json"
    result = cli(*arguments(tmp_path / "missing.stalx", output))
    assert result.returncode != 0
    assert result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()
    assert cli(*arguments(Path(__file__), output)).returncode != 0
