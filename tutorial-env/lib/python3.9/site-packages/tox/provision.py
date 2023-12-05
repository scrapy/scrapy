"""This package handles provisioning an appropriate tox version per requirements."""
from __future__ import annotations

import json
import logging
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import TYPE_CHECKING, List, cast

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from tox.config.loader.memory import MemoryLoader
from tox.execute.api import StdinSource
from tox.plugin import impl
from tox.report import HandledError
from tox.tox_env.errors import Skip
from tox.tox_env.python.pip.req_file import PythonDeps
from tox.tox_env.python.runner import PythonRun

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from tox.session.state import State


@impl
def tox_add_option(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--no-provision",
        default=False,
        const=True,
        nargs="?",
        metavar="REQ_JSON",
        help="do not perform provision, but fail and if a path was provided write provision metadata as JSON to it",
    )
    parser.add_argument(
        "--no-recreate-provision",
        dest="no_recreate_provision",
        help="if recreate is set do not recreate provision tox environment",
        action="store_true",
    )
    parser.add_argument(
        "-r",
        "--recreate",
        dest="recreate",
        help="recreate the tox environments",
        action="store_true",
    )


def provision(state: State) -> int | bool:
    # remove the dev and marker to allow local development of the package
    state.conf.core.add_config(
        keys=["min_version", "minversion"],
        of_type=Version,
        # do not include local version specifier (because it's not allowed in version spec per PEP-440)
        default=None,  # type: ignore[arg-type] # Optional[Version] translates to object
        desc="Define the minimal tox version required to run",
    )
    state.conf.core.add_config(
        keys="provision_tox_env",
        of_type=str,
        default=".tox",
        desc="Name of the virtual environment used to provision a tox.",
    )

    def add_tox_requires_min_version(reqs: list[Requirement]) -> list[Requirement]:
        min_version: Version = state.conf.core["min_version"]
        reqs.append(Requirement(f"tox{f'>={min_version}' if min_version else ''}"))
        return reqs

    state.conf.core.add_config(
        keys="requires",
        of_type=List[Requirement],
        default=[],
        desc="Name of the virtual environment used to provision a tox.",
        post_process=add_tox_requires_min_version,
    )

    from tox.plugin.manager import MANAGER

    MANAGER.tox_add_core_config(state.conf.core, state)

    requires: list[Requirement] = state.conf.core["requires"]
    missing = _get_missing(requires)

    deps = ", ".join(f"{p}{'' if v is None else f' ({v})'}" for p, v in missing)
    loader = MemoryLoader(  # these configuration values are loaded from in-memory always (no file conf)
        base=[],  # disable inheritance for provision environments
        package="skip",  # no packaging for this please
        # use our own dependency specification
        deps=PythonDeps("\n".join(str(r) for r in requires), root=state.conf.core["tox_root"]),
        pass_env=["*"],  # do not filter environment variables, will be handled by provisioned tox
        recreate=state.conf.options.recreate and not state.conf.options.no_recreate_provision,
    )
    provision_tox_env: str = state.conf.core["provision_tox_env"]
    state.conf.memory_seed_loaders[provision_tox_env].append(loader)
    state.envs._mark_provision(bool(missing), provision_tox_env)  # noqa: SLF001

    if not missing:
        return False

    miss_msg = f"is missing [requires (has)]: {deps}"

    no_provision: bool | str = state.conf.options.no_provision
    if no_provision:
        msg = f"provisioning explicitly disabled within {sys.executable}, but {miss_msg}"
        if isinstance(no_provision, str):
            msg += f" and wrote to {no_provision}"
            min_version = str(next(i.specifier for i in requires if i.name == "tox")).split("=")
            requires_dict = {
                "minversion": min_version[1] if len(min_version) >= 2 else None,  # noqa: PLR2004
                "requires": [str(i) for i in requires],
            }
            Path(no_provision).write_text(json.dumps(requires_dict, indent=4))
        raise HandledError(msg)

    logging.warning("will run in automatically provisioned tox, host %s %s", sys.executable, miss_msg)
    return run_provision(provision_tox_env, state)


def _get_missing(requires: list[Requirement]) -> list[tuple[Requirement, str | None]]:
    missing: list[tuple[Requirement, str | None]] = []
    for package in requires:
        package_name = canonicalize_name(package.name)
        try:
            dist = distribution(package_name)
        except PackageNotFoundError:
            missing.append((package, None))
        else:
            if not package.specifier.contains(dist.version, prereleases=True):
                missing.append((package, dist.version))
    return missing


def run_provision(name: str, state: State) -> int:
    tox_env: PythonRun = cast(PythonRun, state.envs[name])
    env_python = tox_env.env_python()
    logging.info("will run in a automatically provisioned python environment under %s", env_python)
    try:
        tox_env.setup()
    except Skip as exception:
        msg = f"cannot provision tox environment {tox_env.conf['env_name']} because {exception}"
        raise HandledError(msg) from exception
    args: list[str] = [str(env_python), "-m", "tox"]
    args.extend(state.args)
    outcome = tox_env.execute(cmd=args, stdin=StdinSource.user_only(), show=True, run_id="provision", cwd=Path.cwd())
    return cast(int, outcome.exit_code)
