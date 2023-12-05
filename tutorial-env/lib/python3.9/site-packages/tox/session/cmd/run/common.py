"""Common functionality shared across multiple type of runs."""
from __future__ import annotations

import logging
import os
import random
import sys
import time
from argparse import Action, ArgumentError, ArgumentParser, Namespace
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from signal import SIGINT, Handlers, signal
from threading import Event, Thread
from typing import TYPE_CHECKING, Any, Iterator, Optional, Sequence, cast

from colorama import Fore

from tox.config.types import EnvList
from tox.execute import Outcome
from tox.journal import write_journal
from tox.session.cmd.run.single import ToxEnvRunResult, run_one
from tox.tox_env.runner import RunToxEnv
from tox.util.ci import is_ci
from tox.util.graph import stable_topological_sort
from tox.util.spinner import MISS_DURATION, Spinner

if TYPE_CHECKING:
    from tox.session.state import State
    from tox.tox_env.api import ToxEnv


class SkipMissingInterpreterAction(Action):
    def __call__(
        self,
        parser: ArgumentParser,  # noqa: ARG002
        namespace: Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,  # noqa: ARG002
    ) -> None:
        value = "true" if values is None else values
        if value not in ("config", "true", "false"):
            raise ArgumentError(self, f"value must be 'config', 'true', or 'false' (got {value!r})")
        setattr(namespace, self.dest, value)


class InstallPackageAction(Action):
    def __call__(
        self,
        parser: ArgumentParser,  # noqa: ARG002
        namespace: Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,  # noqa: ARG002
    ) -> None:
        if not values:
            raise ArgumentError(self, "cannot be empty")
        path = Path(cast(str, values)).absolute()
        if not path.exists():
            raise ArgumentError(self, f"{path} does not exist")
        if not path.is_file():
            raise ArgumentError(self, f"{path} is not a file")
        setattr(namespace, self.dest, path)


def env_run_create_flags(parser: ArgumentParser, mode: str) -> None:  # noqa: C901
    # mode can be one of: run, run-parallel, legacy, devenv, config
    if mode not in ("config", "depends"):
        parser.add_argument(
            "--result-json",
            dest="result_json",
            metavar="path",
            of_type=Path,
            default=None,
            help="write a JSON file with detailed information about all commands and results involved",
        )
    if mode not in ("devenv", "depends"):
        parser.add_argument(
            "-s",
            "--skip-missing-interpreters",
            default="config",
            metavar="v",
            nargs="?",
            action=SkipMissingInterpreterAction,
            help="don't fail tests for missing interpreters: {config,true,false} choice",
        )
    if mode not in ("devenv", "config", "depends"):
        parser.add_argument(
            "-n",
            "--notest",
            dest="no_test",
            help="do not run the test commands",
            action="store_true",
        )
        parser.add_argument(
            "-b",
            "--pkg-only",
            "--sdistonly",
            action="store_true",
            help="only perform the packaging activity",
            dest="package_only",
        )
        parser.add_argument(
            "--installpkg",
            help="use specified package for installation into venv, instead of packaging the project",
            default=None,
            of_type=Optional[Path],
            action=InstallPackageAction,
            dest="install_pkg",
        )
    if mode not in ("devenv", "depends"):
        parser.add_argument(
            "--develop",
            action="store_true",
            help="install package in development mode",
            dest="develop",
        )
    if mode not in ("depends",):

        class SeedAction(Action):
            def __call__(
                self,
                parser: ArgumentParser,  # noqa: ARG002
                namespace: Namespace,
                values: str | Sequence[Any] | None,
                option_string: str | None = None,  # noqa: ARG002
            ) -> None:
                if values == "notset":
                    result = None
                else:
                    try:
                        result = int(cast(str, values))
                        if result <= 0:
                            msg = "must be greater than zero"
                            raise ValueError(msg)  # noqa: TRY301
                    except ValueError as exc:
                        raise ArgumentError(self, str(exc)) from exc
                setattr(namespace, self.dest, result)

        if os.environ.get("PYTHONHASHSEED", "random") != "random":
            hashseed_default = int(os.environ["PYTHONHASHSEED"])
        else:
            hashseed_default = random.randint(1, 1024 if sys.platform == "win32" else 4294967295)  # noqa: S311

        parser.add_argument(
            "--hashseed",
            metavar="SEED",
            help="set PYTHONHASHSEED to SEED before running commands. Defaults to a random integer in the range "
            "[1, 4294967295] ([1, 1024] on Windows). Passing 'notset' suppresses this behavior.",
            action=SeedAction,
            of_type=Optional[int],
            default=hashseed_default,
            dest="hash_seed",
        )
    parser.add_argument(
        "--discover",
        dest="discover",
        nargs="+",
        metavar="path",
        help="for Python discovery first try the Python executables under these paths",
        default=[],
    )
    if mode not in ("depends",):
        parser.add_argument(
            "--no-recreate-pkg",
            dest="no_recreate_pkg",
            help="if recreate is set do not recreate packaging tox environment(s)",
            action="store_true",
        )
        list_deps = parser.add_mutually_exclusive_group()
        list_deps.add_argument(
            "--list-dependencies",
            action="store_true",
            default=is_ci(),
            help="list the dependencies installed during environment setup",
        )
        list_deps.add_argument(
            "--no-list-dependencies",
            action="store_false",
            dest="list_dependencies",
            help="never list the dependencies installed during environment setup",
        )
    if mode not in ("devenv", "config", "depends"):
        parser.add_argument(
            "--skip-pkg-install",
            dest="skip_pkg_install",
            help="skip package installation for this run",
            action="store_true",
        )


def report(start: float, runs: list[ToxEnvRunResult], is_colored: bool, verbosity: int) -> int:  # noqa: FBT001
    def _print(color_: int, message: str) -> None:
        if verbosity:
            print(f"{color_ if is_colored else ''}{message}{Fore.RESET if is_colored else ''}")  # noqa: T201

    successful, skipped = [], []
    for run in runs:
        successful.append(run.code == Outcome.OK or run.ignore_outcome)
        skipped.append(run.skipped)
        duration_individual = [o.elapsed for o in run.outcomes] if verbosity >= 2 else []  # noqa: PLR2004
        extra = f"+cmd[{','.join(f'{i:.2f}' for i in duration_individual)}]" if duration_individual else ""
        setup = run.duration - sum(duration_individual)
        msg, color = _get_outcome_message(run)
        out = f"  {run.name}: {msg} ({run.duration:.2f}{f'=setup[{setup:.2f}]{extra}' if extra else ''} seconds)"
        _print(color, out)

    duration = time.monotonic() - start
    all_good = all(successful) and not all(skipped)
    if all_good:
        _print(Fore.GREEN, f"  congratulations :) ({duration:.2f} seconds)")
        return Outcome.OK
    _print(Fore.RED, f"  evaluation failed :( ({duration:.2f} seconds)")
    if len(runs) == 1:
        return runs[0].code if not runs[0].skipped else -1
    return -1


def _get_outcome_message(run: ToxEnvRunResult) -> tuple[str, int]:
    if run.skipped:
        msg, color = "SKIP", Fore.YELLOW
    elif run.code == Outcome.OK:
        msg, color = "OK", Fore.GREEN
    elif run.ignore_outcome:
        msg, color = f"IGNORED FAIL code {run.code}", Fore.YELLOW
    else:
        msg, color = f"FAIL code {run.code}", Fore.RED
    return msg, color


logger = logging.getLogger(__name__)


def execute(state: State, max_workers: int | None, has_spinner: bool, live: bool) -> int:  # noqa: FBT001
    interrupt, done = Event(), Event()
    results: list[ToxEnvRunResult] = []
    future_to_env: dict[Future[ToxEnvRunResult], ToxEnv] = {}
    state.envs.ensure_only_run_env_is_active()
    to_run_list: list[str] = list(state.envs.iter())
    for name in to_run_list:
        cast(RunToxEnv, state.envs[name]).mark_active()
    previous, has_previous = None, False
    try:
        spinner = ToxSpinner(has_spinner, state, len(to_run_list))
        thread = Thread(
            target=_queue_and_wait,
            name="tox-interrupt",
            args=(state, to_run_list, results, future_to_env, interrupt, done, max_workers, spinner, live),
        )
        thread.start()
        try:
            thread.join()
        except KeyboardInterrupt:
            previous, has_previous = signal(SIGINT, Handlers.SIG_IGN), True
            spinner.print_report = False  # no need to print reports at this point, final report coming up
            logger.error("[%s] KeyboardInterrupt - teardown started", os.getpid())  # noqa: TRY400
            interrupt.set()
            # cancel in reverse order to not allow submitting new jobs as we cancel running ones
            for future, tox_env in reversed(list(future_to_env.items())):
                cancelled = future.cancel()
                # if cannot be cancelled and not done -> still runs
                if cancelled is False and not future.done():  # pragma: no branch
                    tox_env.interrupt()
            done.wait()
            # workaround for https://bugs.python.org/issue45274
            lock = getattr(thread, "_tstate_lock", None)
            if lock is not None and lock.locked():  # pragma: no branch
                lock.release()  # pragma: no cover
                # calling private method to fix thread state
                thread._stop()  # type: ignore[attr-defined] # pragma: no cover # noqa: SLF001
            thread.join()
    finally:
        name_to_run = {r.name: r for r in results}
        ordered_results: list[ToxEnvRunResult] = [name_to_run[env] for env in to_run_list]
        # write the journal
        write_journal(getattr(state.conf.options, "result_json", None), state._journal)  # noqa: SLF001
        # report the outcome
        exit_code = report(
            state.conf.options.start,
            ordered_results,
            state.conf.options.is_colored,
            state.conf.options.verbosity,
        )
        if has_previous:
            signal(SIGINT, previous)
    return exit_code


class ToxSpinner(Spinner):
    def __init__(self, enabled: bool, state: State, total: int) -> None:  # noqa: FBT001
        super().__init__(
            enabled=enabled,
            colored=state.conf.options.is_colored,
            stream=state._options.log_handler.stdout,  # noqa: SLF001
            total=total,
        )

    def update_spinner(self, result: ToxEnvRunResult, success: bool) -> None:  # noqa: FBT001
        done = (self.skip if result.skipped else self.succeed) if success else self.fail
        done(result.name)


def _queue_and_wait(  # noqa: C901, PLR0913, PLR0915
    state: State,
    to_run_list: list[str],
    results: list[ToxEnvRunResult],
    future_to_env: dict[Future[ToxEnvRunResult], ToxEnv],
    interrupt: Event,
    done: Event,
    max_workers: int | None,
    spinner: ToxSpinner,
    live: bool,  # noqa: FBT001
) -> None:
    try:
        options = state._options  # noqa: SLF001
        with spinner:
            max_workers = len(to_run_list) if max_workers is None else max_workers
            completed: set[str] = set()
            envs_to_run_generator = ready_to_run_envs(state, to_run_list, completed)

            def _run(tox_env: RunToxEnv) -> ToxEnvRunResult:
                spinner.add(tox_env.conf.name)
                return run_one(
                    tox_env,
                    options.parsed.no_test or options.parsed.package_only,
                    suspend_display=live is False,
                )

            try:
                executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="tox-driver")
                env_list: list[str] = []
                while True:
                    for env in env_list:  # queue all available
                        tox_env_to_run = cast(RunToxEnv, state.envs[env])
                        if interrupt.is_set():  # queue the rest as failed upfront
                            tox_env_to_run.teardown()
                            future: Future[ToxEnvRunResult] = Future()
                            res = ToxEnvRunResult(name=env, skipped=False, code=-2, outcomes=[], duration=MISS_DURATION)
                            future.set_result(res)
                        else:
                            future = executor.submit(_run, tox_env_to_run)
                        future_to_env[future] = tox_env_to_run

                    if not future_to_env:
                        result: ToxEnvRunResult | None = None
                    else:  # if we have queued wait for completed
                        future = next(as_completed(future_to_env))
                        tox_env_done = future_to_env.pop(future)
                        try:
                            result = future.result()
                        except CancelledError:
                            tox_env_done.teardown()
                            name = tox_env_done.conf.name
                            result = ToxEnvRunResult(
                                name=name,
                                skipped=False,
                                code=-3,
                                outcomes=[],
                                duration=MISS_DURATION,
                            )
                        results.append(result)
                        completed.add(result.name)

                    env_list = next(envs_to_run_generator, [])
                    # if nothing running and nothing more to run we're done
                    final_run = not env_list and not future_to_env
                    if final_run:  # disable report on final env
                        spinner.print_report = False
                    if result is not None:
                        _handle_one_run_done(result, spinner, state, live)
                    if final_run:
                        break

            except BaseException:  # pragma: no cover
                logging.exception("Internal Error")  # pragma: no cover
                raise  # pragma: no cover
            finally:
                executor.shutdown(wait=True)
    finally:
        try:
            # call teardown - configuration only environments for example could not be finished
            for name in to_run_list:
                state.envs[name].teardown()
        finally:
            done.set()


def _handle_one_run_done(
    result: ToxEnvRunResult,
    spinner: ToxSpinner,
    state: State,
    live: bool,  # noqa: FBT001
) -> None:
    success = result.code == Outcome.OK
    spinner.update_spinner(result, success)
    tox_env = cast(RunToxEnv, state.envs[result.name])
    if tox_env.journal:  # add overall journal entry
        tox_env.journal["result"] = {
            "success": success,
            "exit_code": result.code,
            "duration": result.duration,
        }
    if live is False and state.conf.options.parallel_live is False:  # teardown background run
        out_err = tox_env.close_and_read_out_err()  # sync writes from buffer to stdout/stderr
        pkg_out_err_list = []
        for package_env in tox_env.package_envs:
            pkg_out_err = package_env.close_and_read_out_err()
            if pkg_out_err is not None:  # pragma: no branch
                pkg_out_err_list.append(pkg_out_err)
        if not success or tox_env.conf["parallel_show_output"]:
            for pkg_out_err in pkg_out_err_list:
                state._options.log_handler.write_out_err(pkg_out_err)  # pragma: no cover  # noqa: SLF001
            if out_err is not None:  # pragma: no branch # first show package build
                state._options.log_handler.write_out_err(out_err)  # noqa: SLF001


def ready_to_run_envs(state: State, to_run: list[str], completed: set[str]) -> Iterator[list[str]]:
    """Generate tox environments ready to run."""
    order, todo = run_order(state, to_run)
    while order:
        ready_to_run: list[str] = []
        new_order: list[str] = []
        for env in order:  # collect next batch of ready to run
            if todo[env] - completed:
                new_order.append(env)
            else:
                ready_to_run.append(env)
        order = new_order
        yield ready_to_run


def run_order(state: State, to_run: list[str]) -> tuple[list[str], dict[str, set[str]]]:
    to_run_set = set(to_run)
    todo: dict[str, set[str]] = {}
    for env in to_run:
        run_env = cast(RunToxEnv, state.envs[env])
        depends = set(cast(EnvList, run_env.conf["depends"]).envs)
        todo[env] = to_run_set & depends
    order = stable_topological_sort(todo)
    return order, todo
