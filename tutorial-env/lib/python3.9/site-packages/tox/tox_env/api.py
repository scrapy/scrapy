"""Defines the abstract base traits of a tox environment."""
from __future__ import annotations

import fnmatch
import logging
import os
import re
import string
import sys
from abc import ABC, abstractmethod
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, List, NamedTuple, Sequence, Set, cast

from tox.execute.request import ExecuteRequest
from tox.tox_env.errors import Fail, Recreate, Skip
from tox.tox_env.info import Info
from tox.util.path import ensure_empty_dir

if TYPE_CHECKING:
    from tox.config.cli.parser import Parsed
    from tox.config.main import Config
    from tox.config.set_env import SetEnv
    from tox.config.sets import CoreConfigSet, EnvConfigSet
    from tox.execute.api import Execute, ExecuteStatus, Outcome, StdinSource
    from tox.journal import EnvJournal
    from tox.report import OutErr, ToxHandler
    from tox.tox_env.installer import Installer

LOGGER = logging.getLogger(__name__)


class ToxEnvCreateArgs(NamedTuple):
    """Arguments to pass on when creating a tox environment."""

    conf: EnvConfigSet
    core: CoreConfigSet
    options: Parsed
    journal: EnvJournal
    log_handler: ToxHandler


class ToxEnv(ABC):
    """A tox environment."""

    def __init__(self, create_args: ToxEnvCreateArgs) -> None:
        """
        Create a new tox environment.

        :param create_args: tox env create args
        """
        self.journal: EnvJournal = create_args.journal  #: handler to the tox reporting system
        self.conf: EnvConfigSet = create_args.conf  #: the config set to use for this environment
        self.core: CoreConfigSet = create_args.core  #: the core tox config set
        self.options: Parsed = create_args.options  #: CLI options
        self.log_handler: ToxHandler = create_args.log_handler  #: handler to the tox reporting system

        #: encode the run state of various methods (setup/clean/etc)
        self._run_state = {"setup": False, "clean": False, "teardown": False}
        self._paths_private: list[Path] = []  #: a property holding the PATH environment variables
        self._hidden_outcomes: list[Outcome] | None = []
        self._env_vars: dict[str, str] | None = None
        self._env_vars_pass_env: list[str] = []
        self._suspended_out_err: OutErr | None = None
        self._execute_statuses: dict[int, ExecuteStatus] = {}
        self._interrupted = False
        self._log_id = 0

        self.register_config()

    @property
    def cache(self) -> Info:
        return Info(self.env_dir)

    @staticmethod
    @abstractmethod
    def id() -> str:  # noqa: A003
        raise NotImplementedError

    @property
    @abstractmethod
    def executor(self) -> Execute:
        raise NotImplementedError

    @property
    @abstractmethod
    def installer(self) -> Installer[Any]:
        raise NotImplementedError

    def _install(self, arguments: Any, section: str, of_type: str) -> None:
        from tox.plugin.manager import MANAGER

        MANAGER.tox_on_install(self, arguments, section, of_type)
        self.installer.install(arguments, section, of_type)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.conf['env_name']})"

    def register_config(self) -> None:
        self.conf.add_constant(
            keys=["env_name", "envname"],
            desc="the name of the tox environment",
            value=self.conf.name,
        )
        self.conf.add_config(
            keys=["labels"],
            of_type=Set[str],
            default=set(),
            desc="labels attached to the tox environment",
        )
        self.conf.add_config(
            keys=["env_dir", "envdir"],
            of_type=Path,
            default=lambda conf, name: cast(Path, conf.core["work_dir"]) / self.name,  # noqa: ARG005
            desc="directory assigned to the tox environment",
        )
        self.conf.add_config(
            keys=["env_tmp_dir", "envtmpdir"],
            of_type=Path,
            default=lambda conf, name: cast(Path, conf.core["work_dir"]) / self.name / "tmp",  # noqa: ARG005
            desc="a folder that is always reset at the start of the run",
        )
        self.conf.add_config(
            keys=["env_log_dir", "envlogdir"],
            of_type=Path,
            default=lambda conf, name: cast(Path, conf.core["work_dir"]) / self.name / "log",  # noqa: ARG005
            desc="a folder for logging where tox will put logs of tool invocation",
        )
        self.executor.register_conf(self)
        self.conf.default_set_env_loader = self._default_set_env
        self.conf.add_config(
            keys=["platform"],
            of_type=str,
            default="",
            desc="run on platforms that match this regular expression (empty means any platform)",
        )

        def pass_env_post_process(values: list[str]) -> list[str]:
            values.extend(self._default_pass_env())
            result = sorted({k: None for k in values}.keys())
            invalid_chars = set(string.whitespace)
            invalid = [v for v in result if any(c in invalid_chars for c in v)]
            if invalid:
                invalid_repr = ", ".join(repr(i) for i in invalid)
                msg = (
                    f"pass_env values cannot contain whitespace, use comma to have multiple values in a single line,"
                    f" invalid values found {invalid_repr}"
                )
                raise Fail(msg)
            return result

        self.conf.add_config(
            keys=["pass_env", "passenv"],
            of_type=List[str],
            default=[],
            desc="environment variables to pass on to the tox environment",
            post_process=pass_env_post_process,
        )
        self.conf.add_config(
            "parallel_show_output",
            of_type=bool,
            default=False,
            desc="if set to True the content of the output will always be shown  when running in parallel mode",
        )
        self.conf.add_config(
            "recreate",
            of_type=bool,
            default=self._recreate_default,
            desc="always recreate virtual environment if this option is true, otherwise leave it up to tox",
        )
        self.conf.add_config(
            "allowlist_externals",
            of_type=List[str],
            default=[],
            desc="external command glob to allow calling",
        )
        assert self.installer is not None  # noqa: S101 # trigger installer creation to allow config registration

    def _recreate_default(self, conf: Config, value: str | None) -> bool:  # noqa: ARG002
        return cast(bool, self.options.recreate)

    @property
    def env_dir(self) -> Path:
        """:return: the tox environments environment folder"""
        return cast(Path, self.conf["env_dir"])

    @property
    def env_tmp_dir(self) -> Path:
        """:return: the tox environments temp folder"""
        return cast(Path, self.conf["env_tmp_dir"])

    @property
    def env_log_dir(self) -> Path:
        """:return: the tox environments log folder"""
        return cast(Path, self.conf["env_log_dir"])

    @property
    def name(self) -> str:
        return cast(str, self.conf["env_name"])

    def _default_set_env(self) -> dict[str, str]:
        return {}

    def _default_pass_env(self) -> list[str]:
        env = [
            "https_proxy",  # HTTP proxy configuration
            "http_proxy",  # HTTP proxy configuration
            "no_proxy",  # HTTP proxy configuration
            "LANG",  # localization
            "LANGUAGE",  # localization
            "CURL_CA_BUNDLE",  # curl certificates
            "SSL_CERT_FILE",  # https certificates
            "CC",  # C compiler command
            "CFLAGS",  # C compiler flags
            "CCSHARED",  # compiler flags used to build a shared library
            "CXX",  # C++ compiler command
            "CPPFLAGS",  # C++ compiler flags
            "LD_LIBRARY_PATH",  # location of libs
            "LDFLAGS",  # linker flags
            "HOME",  # needed for `os.path.expanduser()` on non-Windows systems
        ]
        if sys.stdout.isatty():  # if we're on a interactive shell pass on the TERM
            env.append("TERM")
        if sys.platform == "win32":  # pragma: win32 cover
            env.extend(
                [
                    "TEMP",  # temporary file location
                    "TMP",  # temporary file location
                    "USERPROFILE",  # needed for `os.path.expanduser()`
                    "PATHEXT",  # needed for discovering executables
                    "MSYSTEM",  # controls paths printed format
                ],
            )
        else:  # pragma: win32 no cover
            env.append("TMPDIR")  # temporary file location
        return env

    def setup(self) -> None:
        """Setup the tox environment."""
        if self._run_state["setup"] is False:  # pragma: no branch
            self._platform_check()
            recreate = cast(bool, self.conf["recreate"])
            if recreate:
                self._clean(transitive=True)
            try:
                self._setup_env()
                self._setup_with_env()
            except Recreate as exception:  # once we might try over
                if not recreate:  # pragma: no cover
                    logging.warning("recreate env because %s", exception.args[0])
                    self._clean(transitive=False)
                    self._setup_env()
                    self._setup_with_env()
            else:
                self._done_with_setup()
            finally:
                self._run_state["setup"] = True

    def teardown(self) -> None:
        if not self._run_state["teardown"]:
            try:
                self._teardown()
            finally:
                from tox.plugin.manager import MANAGER

                MANAGER.tox_env_teardown(self)
                self._run_state["teardown"] = True

    def _teardown(self) -> None:  # noqa: B027 # empty abstract base class
        pass

    def _platform_check(self) -> None:
        """Skip env when platform does not match."""
        platform_str: str = self.conf["platform"]
        if platform_str:
            match = re.fullmatch(platform_str, self.runs_on_platform)
            if match is None:
                msg = f"platform {self.runs_on_platform} does not match {platform_str}"
                raise Skip(msg)

    @property
    @abstractmethod
    def runs_on_platform(self) -> str:
        raise NotImplementedError

    def _setup_env(self) -> None:
        """
        1. env dir exists
        2. contains a runner with the same type.
        """
        conf = {"name": self.conf.name, "type": type(self).__name__}
        with self.cache.compare(conf, ToxEnv.__name__) as (eq, old):
            if eq is False and old is not None:  # pragma: no branch  # recreate if already created and not equals
                msg = f"env type changed from {old} to {conf}"
                raise Recreate(msg)
        self._handle_env_tmp_dir()
        self._handle_core_tmp_dir()

    def _setup_with_env(self) -> None:  # noqa: B027 # empty abstract base class
        pass

    def _done_with_setup(self) -> None:  # noqa: B027 # empty abstract base class
        """Called when setup is done."""

    def _handle_env_tmp_dir(self) -> None:
        """Ensure exists and empty."""
        env_tmp_dir = self.env_tmp_dir
        if env_tmp_dir.exists() and next(env_tmp_dir.iterdir(), None) is not None:
            LOGGER.debug("clear env temp folder %s", env_tmp_dir)
            ensure_empty_dir(env_tmp_dir)
        env_tmp_dir.mkdir(parents=True, exist_ok=True)

    def _handle_core_tmp_dir(self) -> None:
        self.core["temp_dir"].mkdir(parents=True, exist_ok=True)

    def _clean(self, transitive: bool = False) -> None:  # noqa: ARG002, FBT001, FBT002
        if self._run_state["clean"]:  # pragma: no branch
            return  # pragma: no cover
        env_dir = self.env_dir
        if env_dir.exists():
            LOGGER.warning("remove tox env folder %s", env_dir)
            ensure_empty_dir(env_dir, except_filename="file.lock")
        self._log_id = 0  # we deleted logs, so start over counter
        self.cache.reset()
        self._run_state.update({"setup": False, "clean": True})

    @property
    def environment_variables(self) -> dict[str, str]:
        pass_env: list[str] = self.conf["pass_env"]
        set_env: SetEnv = self.conf["set_env"]
        if self._env_vars_pass_env == pass_env and not set_env.changed and self._env_vars is not None:
            return self._env_vars

        result = self._load_pass_env(pass_env)
        # load/paths_env might trigger a load of the environment variables, set result here, returns current state
        self._env_vars, self._env_vars_pass_env, set_env.changed = result, pass_env.copy(), False
        # set PATH here in case setting and environment variable requires access to the environment variable PATH
        result["PATH"] = self._make_path()
        for key in set_env:
            result[key] = set_env.load(key)
        result["TOX_ENV_NAME"] = self.name
        result["TOX_WORK_DIR"] = str(self.core["work_dir"])
        result["TOX_ENV_DIR"] = str(self.conf["env_dir"])
        return result

    @staticmethod
    def _load_pass_env(pass_env: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        patterns = [re.compile(fnmatch.translate(e), re.IGNORECASE) for e in pass_env]
        for env, value in os.environ.items():
            if any(p.match(env) for p in patterns):
                result[env] = value
        return result

    @property
    def _paths(self) -> list[Path]:
        return self._paths_private

    @_paths.setter
    def _paths(self, value: list[Path]) -> None:
        self._paths_private = value
        # also update the environment variable with the new value
        if self._env_vars is not None:  # pragma: no branch
            # remove duplicates and prepend the tox env paths
            result = self._make_path()
            self._env_vars["PATH"] = result

    @property
    def _allow_externals(self) -> list[str]:
        result: list[str] = [f"{i}{os.sep}*" for i in self._paths]
        result.extend(i.strip() for i in self.conf["allowlist_externals"])
        return result

    def _make_path(self) -> str:
        values = dict.fromkeys(str(i) for i in self._paths)
        values.update(dict.fromkeys(os.environ.get("PATH", "").split(os.pathsep)))
        return os.pathsep.join(values)

    def execute(  # noqa: PLR0913
        self,
        cmd: Sequence[Path | str],
        stdin: StdinSource,
        show: bool | None = None,
        cwd: Path | None = None,
        run_id: str = "",
        executor: Execute | None = None,
    ) -> Outcome:
        with self.execute_async(cmd, stdin, show, cwd, run_id, executor) as status:
            while status.wait() is None:
                pass  # pragma: no cover
        if status.outcome is None:  # pragma: no cover # this should not happen
            raise RuntimeError  # pragma: no cover
        return status.outcome

    def interrupt(self) -> None:
        """Interrupt the execution of a tox environment."""
        logging.warning("interrupt tox environment: %s", self.conf.name)
        self._interrupted = True
        for status in list(self._execute_statuses.values()):
            status.interrupt()

    @contextmanager
    def execute_async(  # noqa: PLR0913
        self,
        cmd: Sequence[Path | str],
        stdin: StdinSource,
        show: bool | None = None,
        cwd: Path | None = None,
        run_id: str = "",
        executor: Execute | None = None,
    ) -> Iterator[ExecuteStatus]:
        if self._interrupted:
            raise SystemExit(-2)  # pragma: no cover
        if cwd is None:
            cwd = self.core["tox_root"]
        if show is None:
            show = self.options.verbosity > 3  # noqa: PLR2004
        request = ExecuteRequest(cmd, cwd, self.environment_variables, stdin, run_id, allow=self._allow_externals)
        if request.cwd == _CWD:
            repr_cwd = ""
        else:
            try:
                repr_cwd = f" {_CWD.relative_to(cwd)}"
            except ValueError:
                repr_cwd = f" {cwd}"
        LOGGER.warning("%s%s> %s", run_id, repr_cwd, request.shell_cmd)
        out_err = self.log_handler.stdout, self.log_handler.stderr
        if executor is None:
            executor = self.executor
        with self._execute_call(executor, out_err, request, show) as execute_status:
            execute_id = id(execute_status)
            try:
                self._execute_statuses[execute_id] = execute_status
                yield execute_status
            finally:
                self._execute_statuses.pop(execute_id)
        if show and self._hidden_outcomes is not None and execute_status.outcome is not None:
            # if it gets cancelled before even starting
            self._hidden_outcomes.append(execute_status.outcome)
        if self.journal and execute_status.outcome is not None:
            self.journal.add_execute(execute_status.outcome, run_id)
        self._log_execute(request, execute_status)

    def _log_execute(self, request: ExecuteRequest, status: ExecuteStatus) -> None:
        if self._log_id == 0:  # start with fresh slate on new run
            ensure_empty_dir(self.env_log_dir)
        self._log_id += 1
        self._write_execute_log(self.name, self.env_log_dir / f"{self._log_id}-{request.run_id}.log", request, status)

    @staticmethod
    def _write_execute_log(env_name: str, log_file: Path, request: ExecuteRequest, status: ExecuteStatus) -> None:
        with log_file.open("wt", encoding="utf-8") as file:
            file.write(f"name: {env_name}\n")
            file.write(f"run_id: {request.run_id}\n")
            for env_key, env_value in request.env.items():
                file.write(f"env {env_key}: {env_value}\n")
            for meta_key, meta_value in status.metadata.items():
                file.write(f"metadata {meta_key}: {meta_value}\n")
            file.write(f"cwd: {request.cwd}\n")
            allow = ["*"] if request.allow is None else request.allow
            file.write(f"allow: {':'.join(allow)}\n")
            file.write(f"cmd: {request.shell_cmd}\n")
            file.write(f"exit_code: {status.exit_code}\n")
        with log_file.open("ab") as file_b:
            if status.out:
                file_b.write(status.out)
            if status.err:  # pragma: no branch
                file_b.write(os.linesep.encode())
                file_b.write(b"standard error:")
                file_b.write(os.linesep.encode())
                file_b.write(status.err)

    @contextmanager
    def _execute_call(
        self,
        executor: Execute,
        out_err: OutErr,
        request: ExecuteRequest,
        show: bool,  # noqa: FBT001
    ) -> Iterator[ExecuteStatus]:
        with executor.call(
            request=request,
            env=self,
            show=show,
            out_err=out_err,
        ) as execute_status:
            yield execute_status

    @contextmanager
    def display_context(self, suspend: bool) -> Iterator[None]:  # noqa: FBT001
        with self._log_context(), self.log_handler.suspend_out_err(suspend, self._suspended_out_err) as out_err:
            if suspend:  # only set if suspended
                self._suspended_out_err = out_err
            yield

    def close_and_read_out_err(self) -> tuple[bytes, bytes] | None:
        if self._suspended_out_err is None:  # pragma: no branch
            return None  # pragma: no cover
        (out, err), self._suspended_out_err = self._suspended_out_err, None
        out_b, err_b = cast(BytesIO, out.buffer).getvalue(), cast(BytesIO, err.buffer).getvalue()
        out.close()
        err.close()
        return out_b, err_b

    @contextmanager
    def _log_context(self) -> Iterator[None]:
        with self.log_handler.with_context(self.conf.name):
            yield

    @property
    def _has_display_suspended(self) -> bool:
        return self._suspended_out_err is not None


_CWD = Path.cwd()
