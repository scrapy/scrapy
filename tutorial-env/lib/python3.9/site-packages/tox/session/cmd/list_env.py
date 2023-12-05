"""Print available tox environments."""
from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING

from tox.plugin import impl
from tox.session.env_select import register_env_select_flags

if TYPE_CHECKING:
    from tox.config.cli.parser import ToxParser
    from tox.session.state import State


@impl
def tox_add_option(parser: ToxParser) -> None:
    our = parser.add_command("list", ["l"], "list environments", list_env)
    our.add_argument("--no-desc", action="store_true", help="do not show description", dest="list_no_description")
    d = register_env_select_flags(our, default=None, group_only=True)
    d.add_argument("-d", action="store_true", help="list just default envs", dest="list_default_only")


def list_env(state: State) -> int:
    option = state.conf.options
    has_group_select = bool(option.factors or option.labels)
    active_only = has_group_select or option.list_default_only

    active = dict.fromkeys(state.envs.iter())
    inactive = {} if active_only else {env: None for env in state.envs.iter(only_active=False) if env not in active}

    if not has_group_select and not option.list_no_description and active:
        print("default environments:")  # noqa: T201
    max_length = max((len(env) for env in chain(active, inactive)), default=0)

    def report_env(name: str) -> None:
        if not option.list_no_description:
            tox_env = state.envs[name]
            text = tox_env.conf["description"]
            if not text.strip():
                text = "[no description]"
            text = text.replace("\n", " ")
            msg = f"{env.ljust(max_length)} -> {text}".strip()
        else:
            msg = env
        print(msg)  # noqa: T201

    for env in active:
        report_env(env)

    if not has_group_select and not option.list_default_only and inactive:
        if not option.list_no_description:
            if active:  # pragma: no branch
                print("")  # noqa: T201
            print("additional environments:")  # noqa: T201
        for env in inactive:
            report_env(env)
    return 0
