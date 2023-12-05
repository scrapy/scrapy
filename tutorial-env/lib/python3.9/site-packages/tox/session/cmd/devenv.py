from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from tox.config.loader.memory import MemoryLoader
from tox.plugin import impl
from tox.report import HandledError
from tox.session.cmd.run.common import env_run_create_flags
from tox.session.cmd.run.sequential import run_sequential
from tox.session.env_select import CliEnv, register_env_select_flags

if TYPE_CHECKING:
    from tox.config.cli.parser import ToxParser
    from tox.session.state import State


@impl
def tox_add_option(parser: ToxParser) -> None:
    help_msg = "sets up a development environment at ENVDIR based on the tox configuration specified "
    our = parser.add_command("devenv", ["d"], help_msg, devenv)
    our.add_argument("devenv_path", metavar="path", default=Path("venv"), nargs="?", type=Path)
    register_env_select_flags(our, default=CliEnv("py"), multiple=False)
    env_run_create_flags(our, mode="devenv")


def devenv(state: State) -> int:
    opt = state.conf.options
    opt.devenv_path = opt.devenv_path.absolute()
    opt.skip_missing_interpreters = False  # the target python must exist
    opt.no_test = False  # do not run the test suite
    opt.package_only = False
    opt.install_pkg = None  # no explicit packages to install
    opt.skip_pkg_install = False  # always install a package in this case
    opt.no_test = True  # do not run the test phase
    loader = MemoryLoader(  # these configuration values are loaded from in-memory always (no file conf)
        usedevelop=True,  # dev environments must be of type dev
        env_dir=opt.devenv_path,  # move it in source
    )
    state.conf.memory_seed_loaders[next(iter(opt.env))].append(loader)

    state.envs.ensure_only_run_env_is_active()
    envs = list(state.envs.iter())
    if len(envs) != 1:
        msg = f"exactly one target environment allowed in devenv mode but found {', '.join(envs)}"
        raise HandledError(msg)
    result = run_sequential(state)
    if result == 0:
        logging.warning("created development environment under %s", opt.devenv_path)
    return result
