from __future__ import annotations

import sys
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from packaging.version import Version

from tox.plugin import impl
from tox.version import version as __version__

if TYPE_CHECKING:
    from tox.config.cli.parser import ToxParser
    from tox.session.state import State


@impl
def tox_add_option(parser: ToxParser) -> None:
    our = parser.add_command(
        "quickstart",
        ["q"],
        "Command line script to quickly create a tox config file for a Python project",
        quickstart,
    )
    our.add_argument(
        "quickstart_root",
        metavar="root",
        default=Path().absolute(),
        nargs="?",
        help="folder to create the tox.ini file",
        type=Path,
    )


def quickstart(state: State) -> int:
    root = state.conf.options.quickstart_root.absolute()
    tox_ini = root / "tox.ini"
    if tox_ini.exists():
        print(f"{tox_ini} already exist, refusing to overwrite")  # noqa: T201
        return 1
    version = str(Version(__version__.split("+")[0]))
    text = f"""
        [tox]
        env_list =
            py{''.join(str(i) for i in sys.version_info[0:2])}
        minversion = {version}

        [testenv]
        description = run the tests with pytest
        package = wheel
        wheel_build_env = .pkg
        deps =
            pytest>=6
        commands =
            pytest {{tty:--color=yes}} {{posargs}}
    """
    content = dedent(text).lstrip()

    print(f"tox {__version__} quickstart utility, will create {tox_ini}:")  # noqa: T201
    print(content, end="")  # noqa: T201

    root.mkdir(parents=True, exist_ok=True)
    tox_ini.write_text(content)
    return 0
