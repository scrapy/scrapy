"""Execute a command in a tox environment."""
from __future__ import annotations

from typing import TYPE_CHECKING

from tox.config.loader.memory import MemoryLoader
from tox.config.types import Command
from tox.plugin import impl
from tox.report import HandledError
from tox.session.cmd.run.common import env_run_create_flags
from tox.session.cmd.run.sequential import run_sequential
from tox.session.env_select import CliEnv, register_env_select_flags

if TYPE_CHECKING:
    from pathlib import Path

    from tox.config.cli.parser import ToxParser
    from tox.session.state import State


@impl
def tox_add_option(parser: ToxParser) -> None:
    our = parser.add_command("exec", ["e"], "execute an arbitrary command within a tox environment", exec_)
    our.epilog = "For example: tox exec -e py39 -- python --version"
    register_env_select_flags(our, default=CliEnv("py"), multiple=False)
    env_run_create_flags(our, mode="exec")


def exec_(state: State) -> int:
    envs = list(state.envs.iter())
    if len(envs) != 1:
        msg = f"exactly one target environment allowed in exec mode but found {', '.join(envs)}"
        raise HandledError(msg)
    loader = MemoryLoader(  # these configuration values are loaded from in-memory always (no file conf)
        commands_pre=[],
        commands=[],
        commands_post=[],
    )
    conf = state.envs[envs[0]].conf
    conf.loaders.insert(0, loader)
    to_path: Path | None = conf["change_dir"] if conf["args_are_paths"] else None
    pos_args = state.conf.pos_args(to_path)
    if not pos_args:
        msg = "You must specify a command as positional arguments, use -- <command>"
        raise HandledError(msg)
    loader.raw["commands"] = [Command(list(pos_args))]
    return run_sequential(state)
