from __future__ import annotations  # noqa: D100

import argparse
import os
import pathlib
import sys
from typing import TYPE_CHECKING

from ._via_fresh_subprocess import SubprocessFrontend

if TYPE_CHECKING:
    from ._frontend import EditableResult, SdistResult, WheelResult


def main_parser() -> argparse.ArgumentParser:  # noqa: D103
    parser = argparse.ArgumentParser(
        description=(
            "A pyproject.toml-based build frontend. "
            "This is mainly useful for debugging PEP-517 backends. "
            "This frontend will not do things like install required build dependencies."
        ),
    )
    parser.add_argument(
        "srcdir",
        type=pathlib.Path,
        nargs="?",
        default=pathlib.Path.cwd(),
        help="source directory (defaults to current directory)",
    )
    parser.add_argument(
        "--sdist",
        "-s",
        dest="distributions",
        action="append_const",
        const="sdist",
        default=[],
        help="build a source distribution",
    )
    parser.add_argument(
        "--wheel",
        "-w",
        dest="distributions",
        action="append_const",
        const="wheel",
        help="build a wheel distribution",
    )
    parser.add_argument(
        "--editable",
        "-e",
        dest="distributions",
        action="append_const",
        const="editable",
        help="build an editable wheel distribution",
    )
    parser.add_argument(
        "--outdir",
        "-o",
        type=pathlib.Path,
        help=f"output directory (defaults to {{srcdir}}{os.sep}dist)",
    )
    return parser


def main(argv: list[str]) -> None:  # noqa: D103
    parser = main_parser()
    args = parser.parse_args(argv)

    outdir = args.outdir or args.srcdir / "dist"
    # we intentionally do not build editable distributions by default
    distributions = args.distributions or ["sdist", "wheel"]

    frontend = SubprocessFrontend(*SubprocessFrontend.create_args_from_folder(args.srcdir)[:-1])
    res: SdistResult | WheelResult | EditableResult

    if "sdist" in distributions:
        print("Building sdist...")  # noqa: T201
        res = frontend.build_sdist(outdir)
        print(res.out)  # noqa: T201
        print(res.err, file=sys.stderr)  # noqa: T201

    if "wheel" in distributions:
        print("Building wheel...")  # noqa: T201
        res = frontend.build_wheel(outdir)
        print(res.out)  # noqa: T201
        print(res.err, file=sys.stderr)  # noqa: T201

    if "editable" in distributions:
        print("Building editable wheel...")  # noqa: T201
        res = frontend.build_editable(outdir)
        print(res.out)  # noqa: T201
        print(res.err, file=sys.stderr)  # noqa: T201


if __name__ == "__main__":
    main(sys.argv[1:])
