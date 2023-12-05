from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from packaging.requirements import InvalidRequirement, Requirement

from tox.config.cli.parser import DEFAULT_VERBOSITY, Parsed, ToxParser
from tox.config.loader.memory import MemoryLoader
from tox.config.set_env import SetEnv
from tox.plugin import impl
from tox.session.cmd.run.common import env_run_create_flags
from tox.session.cmd.run.parallel import OFF_VALUE, parallel_flags, run_parallel
from tox.session.cmd.run.sequential import run_sequential
from tox.session.env_select import CliEnv, EnvSelector, register_env_select_flags
from tox.tox_env.python.pip.req_file import PythonDeps

from .devenv import devenv
from .list_env import list_env
from .show_config import show_config

if TYPE_CHECKING:
    from tox.session.state import State


@impl
def tox_add_option(parser: ToxParser) -> None:
    our = parser.add_command("legacy", ["le"], "legacy entry-point command", legacy)
    our.add_argument("--help-ini", "--hi", action="store_true", help="show live configuration", dest="show_config")
    our.add_argument(
        "--showconfig",
        action="store_true",
        help="show live configuration (by default all env, with -l only default targets, specific via TOXENV/-e)",
        dest="show_config",
    )
    our.add_argument(
        "-a",
        "--listenvs-all",
        action="store_true",
        help="show list of all defined environments (with description if verbose)",
        dest="list_envs_all",
    )
    our.add_argument(
        "-l",
        "--listenvs",
        action="store_true",
        help="show list of test environments (with description if verbose)",
        dest="list_envs",
    )
    our.add_argument(
        "--devenv",
        help="sets up a development environment at ENVDIR based on the env's tox configuration specified by"
        "`-e` (-e defaults to py)",
        dest="devenv_path",
        metavar="ENVDIR",
        default=None,
        of_type=Path,
    )
    register_env_select_flags(our, default=CliEnv())
    env_run_create_flags(our, mode="legacy")
    parallel_flags(our, default_parallel=OFF_VALUE, no_args=True)
    our.add_argument(
        "--pre",
        action="store_true",
        help="deprecated use PIP_PRE in set_env instead - install pre-releases and development versions of"
        "dependencies; this will set PIP_PRE=1 environment variable",
    )
    our.add_argument(
        "--force-dep",
        action="append",
        metavar="req",
        default=[],
        help="Forces a certain version of one of the dependencies when configuring the virtual environment. REQ "
        "Examples 'pytest<6.1' or 'django>=2.2'.",
        type=Requirement,
    )
    our.add_argument(
        "--sitepackages",
        action="store_true",
        help="deprecated use VIRTUALENV_SYSTEM_SITE_PACKAGES=1, override sitepackages setting to True in all envs",
        dest="site_packages",
    )
    our.add_argument(
        "--alwayscopy",
        action="store_true",
        help="deprecated use VIRTUALENV_ALWAYS_COPY=1, override always copy setting to True in all envs",
        dest="always_copy",
    )


def legacy(state: State) -> int:
    option = state.conf.options
    if option.show_config:
        option.list_keys_only = []
        option.show_core = not bool(option.env)
    if option.list_envs or option.list_envs_all:
        state.envs.on_empty_fallback_py = False
        option.list_no_description = option.verbosity <= DEFAULT_VERBOSITY
        option.list_default_only = not option.list_envs_all
        option.show_core = False

    _handle_legacy_only_flags(option, state.envs)

    if option.show_config:
        return show_config(state)
    if option.list_envs or option.list_envs_all:
        return list_env(state)
    if option.devenv_path:
        if option.env.is_default_list:
            option.env = CliEnv(["py"])
        option.devenv_path = Path(option.devenv_path)
        return devenv(state)
    if option.parallel != 0:  # only 0 means sequential
        return run_parallel(state)
    return run_sequential(state)


def _handle_legacy_only_flags(option: Parsed, envs: EnvSelector) -> None:  # noqa: C901
    override = {}
    if getattr(option, "site_packages", False):
        override["system_site_packages"] = True
    if getattr(option, "always_copy", False):
        override["always_copy"] = True
    set_env = {}
    if getattr(option, "pre", False):
        set_env["PIP_PRE"] = "1"
    forced = {j.name: j for j in getattr(option, "force_dep", [])}
    if override or set_env or forced:
        for env in envs.iter(only_active=True, package=False):
            env_conf = envs[env].conf
            if override:
                env_conf.loaders.insert(0, MemoryLoader(**override))
            if set_env:
                cast(SetEnv, env_conf["set_env"]).update(set_env, override=True)
            if forced:
                to_force = forced.copy()
                deps = cast(PythonDeps, env_conf["deps"])
                as_root_args = deps.as_root_args
                for at, entry in enumerate(as_root_args):
                    try:
                        req = Requirement(entry)
                    except InvalidRequirement:
                        continue
                    if req.name in to_force:
                        as_root_args[at] = str(to_force[req.name])
                        del to_force[req.name]
                as_root_args.extend(str(v) for v in to_force.values())
