"""Command-line entry point."""

import argparse
import sys

from stalagmight_lib import __version__
from stalagmight_lib.commands.convert import convert
from stalagmight_lib.exceptions import StalagmightError


def main():
    parser = argparse.ArgumentParser(prog="stalagmight")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("command", choices=["convert"])
    parser.add_argument("args", help=argparse.SUPPRESS, nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        return convert(args.args)
    except (StalagmightError, OSError) as exc:
        sys.stderr.write(f"stalagmight: {exc}\n")
        return 1
