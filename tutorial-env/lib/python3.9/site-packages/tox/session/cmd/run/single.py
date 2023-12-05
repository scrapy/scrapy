"""Defines how to run a single tox environment."""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, NamedTuple, cast

from tox.execute.api import Outcome, StdinSource
from tox.tox_env.errors import Fail, Skip
from tox.tox_env.python.virtual_env.package.pyproject import ToxBackendFailed

if TYPE_CHECKING:
    from pathlib import Path

    from tox.config.types import Command
    from tox.tox_env.api import ToxEnv
    from tox.tox_env.runner import RunToxEnv

LOGGER = logging.getLogger(__name__)


class ToxEnvRunResult(NamedTuple):
    name: str
    skipped: bool
    code: int
    outcomes: list[Outcome]
    duration: float
    ignore_outcome: bool = False


def run_one(tox_env: RunToxEnv, no_test: bool, suspend_display: bool) -> ToxEnvRunResult:  # noqa: FBT001
    start_one = time.monotonic()
    name = tox_env.conf.name
    with tox_env.display_context(suspend_display):
        skipped, code, outcomes = _evaluate(tox_env, no_test)
    duration = time.monotonic() - start_one
    return ToxEnvRunResult(name, skipped, code, outcomes, duration, tox_env.conf["ignore_outcome"])


def _evaluate(tox_env: RunToxEnv, no_test: bool) -> tuple[bool, int, list[Outcome]]:  # noqa: FBT001
    skipped = False
    code: int = 0
    outcomes: list[Outcome] = []
    try:
        try:
            tox_env.setup()
            code, outcomes = run_commands(tox_env, no_test)
        except Skip as exception:
            LOGGER.warning("skipped because %s", exception)
            code = 0
            skipped = True
        except ToxBackendFailed as exception:
            LOGGER.error("%s", exception)  # noqa: TRY400
            raise SystemExit(exception.code)  # noqa: B904, TRY200
        except Fail as exception:
            LOGGER.error("failed with %s", exception)  # noqa: TRY400
            code = 1
        except Exception:  # pragma: no cover
            LOGGER.exception("internal error")  # pragma: no cover
            code = 2  # pragma: no cover
        finally:
            tox_env.teardown()
    except SystemExit as exception:  # setup command fails (interrupted or via invocation)
        code = cast(int, exception.code)
    return skipped, code, outcomes


def run_commands(tox_env: RunToxEnv, no_test: bool) -> tuple[int, list[Outcome]]:  # noqa: FBT001
    outcomes: list[Outcome] = []
    if no_test:
        exit_code = Outcome.OK
    else:
        from tox.plugin.manager import MANAGER  # importing this here to avoid circular import

        chdir: Path = tox_env.conf["change_dir"]
        chdir.mkdir(exist_ok=True, parents=True)
        ignore_errors: bool = tox_env.conf["ignore_errors"]
        MANAGER.tox_before_run_commands(tox_env)
        status_pre, status_main, status_post = -1, -1, -1
        try:
            try:
                status_pre = run_command_set(tox_env, "commands_pre", chdir, ignore_errors, outcomes)
                if status_pre == Outcome.OK or ignore_errors:
                    status_main = run_command_set(tox_env, "commands", chdir, ignore_errors, outcomes)
                else:
                    status_main = Outcome.OK
            finally:
                status_post = run_command_set(tox_env, "commands_post", chdir, ignore_errors, outcomes)
        finally:
            exit_code = status_pre or status_main or status_post  # first non-success
            MANAGER.tox_after_run_commands(tox_env, exit_code, outcomes)
    return exit_code, outcomes


def run_command_set(
    tox_env: ToxEnv,
    key: str,
    cwd: Path,
    ignore_errors: bool,  # noqa: FBT001
    outcomes: list[Outcome],
) -> int:
    exit_code = Outcome.OK
    command_set: list[Command] = tox_env.conf[key]
    for at, cmd in enumerate(command_set):
        current_outcome = tox_env.execute(
            cmd.args,
            cwd=cwd,
            stdin=StdinSource.user_only(),
            show=True,
            run_id=f"{key}[{at}]",
        )
        outcomes.append(current_outcome)
        try:
            current_outcome.assert_success()
        except SystemExit as exception:
            if cmd.ignore_exit_code:
                logging.warning("command failed but is marked ignore outcome so handling it as success")
                continue
            if ignore_errors:
                if exit_code == Outcome.OK:
                    exit_code = cast(int, exception.code)  # ignore errors continues ahead but saves the exit code
                continue
            return cast(int, exception.code)
    return exit_code


__all__ = (
    "run_one",
    "run_command_set",
    "ToxEnvRunResult",
)
