"""Export supported native survey data as JSON."""

import argparse
from pathlib import Path

from stalagmight_lib.exceptions import StalagmightFormatError
from stalagmight_lib.parser import read_stalx


def convert(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="stalagmight convert")
    parser.add_argument(
        "-i",
        "--input_file",
        type=Path,
        required=True,
        help="Source schema-18 .stalx survey",
    )
    parser.add_argument("-o", "--output_file", type=Path, required=True)
    parser.add_argument("-f", "--format", choices=["json"], required=True)
    parser.add_argument("-w", "--overwrite", action="store_true")
    parsed = parser.parse_args(args)
    source, output = parsed.input_file, parsed.output_file
    if source.resolve() == output.resolve() or (
        output.exists() and source.samefile(output)
    ):
        raise StalagmightFormatError("Output refers to the input file")
    if output.exists() and not parsed.overwrite:
        raise FileExistsError(f"{output} exists; use --overwrite to replace it")
    survey = read_stalx(source)
    with output.open("w" if parsed.overwrite else "x", encoding="utf-8") as stream:
        stream.write(survey.model_dump_json(indent=2))
    return 0
