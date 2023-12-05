"""A pytest plugin useful to test tox itself (and its plugins)."""
from __future__ import annotations

import inspect
import os
import re
import shutil
import socket
import sys
import textwrap
import warnings
from contextlib import closing, contextmanager
from pathlib import Path
from types import ModuleType, TracebackType
from typing import TYPE_CHECKING, Any, Callable, Iterator, Protocol, Sequence, cast

import pytest
from _pytest.fixtures import SubRequest
from devpi_process import IndexServer
from virtualenv.info import fs_supports_symlink

import tox.run
from tox.execute.api import Execute, ExecuteInstance, ExecuteOptions, ExecuteStatus, Outcome
from tox.execute.request import ExecuteRequest, shell_cmd
from tox.plugin import manager
from tox.report import LOGGER, OutErr
from tox.run import run as tox_run
from tox.run import setup_state as previous_setup_state
from tox.session.cmd.run.parallel import ENV_VAR_KEY
from tox.tox_env import api as tox_env_api
from tox.tox_env.api import ToxEnv

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture

    from tox.config.sets import EnvConfigSet
    from tox.execute.stream import SyncWrite
    from tox.session.state import State

    CaptureFixture = pytest.CaptureFixture[str]
else:
    CaptureFixture = pytest.CaptureFixture

os.environ["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
os.environ["PIP_NO_PYTHON_VERSION_WARNING"] = "1"

if fs_supports_symlink():  # pragma: no cover # used to speed up test suite run time where possible
    os.environ["VIRTUALENV_SYMLINK_APP_DATA"] = "1"
    os.environ["VIRTUALENV_SYMLINKS"] = "1"


@pytest.fixture(autouse=True)
def ensure_logging_framework_not_altered() -> Iterator[None]:  # noqa: PT004
    before_handlers = list(LOGGER.handlers)
    yield
    LOGGER.handlers = before_handlers


@pytest.fixture(autouse=True)
def _disable_root_tox_py(request: SubRequest, mocker: MockerFixture) -> Iterator[None]:
    """Unless this is a plugin test do not allow loading toxfile.py."""
    if request.node.get_closest_marker("plugin_test"):  # unregister inline plugin
        module, load_inline = None, manager._load_inline  # noqa: SLF001

        def _load_inline(path: Path) -> ModuleType | None:  # register only on first run, and unregister at end
            nonlocal module
            module = load_inline(path)
            return module

        mocker.patch.object(manager, "_load_inline", _load_inline)
        yield
        if module is not None:  # pragma: no branch
            manager.MANAGER.manager.unregister(module)
    else:  # do not allow loading inline plugins
        mocker.patch("tox.plugin.inline._load_plugin", return_value=None)
        yield


@contextmanager
def check_os_environ() -> Iterator[None]:
    old = os.environ.copy()
    to_clean = {k: os.environ.pop(k, None) for k in (ENV_VAR_KEY, "TOX_WORK_DIR", "PYTHONPATH", "COV_CORE_CONTEXT")}

    yield

    for key, value in to_clean.items():
        if value is not None:
            os.environ[key] = value

    new = os.environ
    extra = {k: new[k] for k in set(new) - set(old)}
    extra.pop("PLAT", None)
    miss = {k: old[k] for k in set(old) - set(new)}
    diff = {
        f"{k} = {old[k]} vs {new[k]}" for k in set(old) & set(new) if old[k] != new[k] and not k.startswith("PYTEST_")
    }
    if extra or miss or diff:
        msg = "test changed environ"
        if extra:
            msg += f" extra {extra}"
        if miss:
            msg += f" miss {miss}"
        if diff:
            msg += f" diff {diff}"
        pytest.fail(msg)


@pytest.fixture(autouse=True)
def check_os_environ_stable(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:  # noqa: PT004
    with check_os_environ():
        yield
        monkeypatch.undo()


@pytest.fixture(autouse=True)
def no_color(monkeypatch: pytest.MonkeyPatch, check_os_environ_stable: None) -> None:  # noqa: ARG001, PT004
    monkeypatch.setenv("NO_COLOR", "yes")


class ToxProject:
    def __init__(  # noqa: PLR0913
        self,
        files: dict[str, Any],
        base: Path | None,
        path: Path,
        capfd: CaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
        mocker: MockerFixture,
    ) -> None:
        self.path: Path = path
        self.monkeypatch: pytest.MonkeyPatch = monkeypatch
        self.mocker = mocker
        self._capfd = capfd
        self._setup_files(self.path, base, files)

    @staticmethod
    def _setup_files(dest: Path, base: Path | None, content: dict[str, Any]) -> None:
        if base is not None:
            shutil.copytree(str(base), str(dest))
        dest.mkdir(exist_ok=True)
        for key, value in content.items():
            if not isinstance(key, str):
                msg = f"{key!r} at {dest}"
                raise TypeError(msg)  # pragma: no cover
            at_path = dest / key
            if callable(value):
                value = textwrap.dedent("\n".join(inspect.getsourcelines(value)[0][1:]))  # noqa: PLW2901
                value = f"from __future__ import annotations\n{value}"  # noqa: PLW2901
            if isinstance(value, dict):
                at_path.mkdir(exist_ok=True)
                ToxProject._setup_files(at_path, None, value)
            elif isinstance(value, str):
                at_path.write_text(textwrap.dedent(value), encoding="utf-8")
            elif value is None:
                at_path.mkdir()
            else:
                msg = f"could not handle {at_path / key} with content {value!r}"  # pragma: no cover
                raise TypeError(msg)  # pragma: no cover

    def patch_execute(self, handle: Callable[[ExecuteRequest], int | None]) -> MagicMock:  # noqa: C901
        class MockExecute(Execute):
            def __init__(self, colored: bool, exit_code: int) -> None:  # noqa: FBT001
                self.exit_code = exit_code
                super().__init__(colored)

            def build_instance(
                self,
                request: ExecuteRequest,
                options: ExecuteOptions,
                out: SyncWrite,
                err: SyncWrite,
            ) -> ExecuteInstance:
                return MockExecuteInstance(request, options, out, err, self.exit_code)

        class MockExecuteStatus(ExecuteStatus):
            def __init__(self, options: ExecuteOptions, out: SyncWrite, err: SyncWrite, exit_code: int) -> None:
                super().__init__(options, out, err)
                self._exit_code = exit_code

            @property
            def exit_code(self) -> int | None:
                return self._exit_code

            def wait(self, timeout: float | None = None) -> int | None:  # noqa: ARG002
                return self._exit_code

            def write_stdin(self, content: str) -> None:  # noqa: ARG002
                return None  # pragma: no cover

            def interrupt(self) -> None:
                return None  # pragma: no cover

        class MockExecuteInstance(ExecuteInstance):
            def __init__(  # noqa: PLR0913
                self,
                request: ExecuteRequest,
                options: ExecuteOptions,
                out: SyncWrite,
                err: SyncWrite,
                exit_code: int,
            ) -> None:
                super().__init__(request, options, out, err)
                self.exit_code = exit_code

            def __enter__(self) -> ExecuteStatus:
                return MockExecuteStatus(self.options, self._out, self._err, self.exit_code)

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> None:
                pass

            @property
            def cmd(self) -> Sequence[str]:
                return self.request.cmd

        @contextmanager
        def _execute_call(
            self: ToxEnv,
            executor: Execute,
            out_err: OutErr,
            request: ExecuteRequest,
            show: bool,  # noqa: FBT001
        ) -> Iterator[ExecuteStatus]:
            exit_code = handle(request)
            if exit_code is not None:
                executor = MockExecute(colored=executor._colored, exit_code=exit_code)  # noqa: SLF001
            with original_execute_call(self, executor, out_err, request, show) as status:
                yield status

        original_execute_call = ToxEnv._execute_call  # noqa: SLF001
        return self.mocker.patch.object(ToxEnv, "_execute_call", side_effect=_execute_call, autospec=True)

    @property
    def structure(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for dir_name, _, files in os.walk(str(self.path)):
            dir_path = Path(dir_name)
            into = result
            relative = dir_path.relative_to(str(self.path))
            for elem in relative.parts:
                into = into.setdefault(elem, {})
            for file_name in files:
                into[file_name] = (dir_path / file_name).read_text()
        return result

    @contextmanager
    def chdir(self, to: Path | None = None) -> Iterator[None]:
        cur_dir = Path.cwd()
        os.chdir(to or self.path)
        try:
            yield
        finally:
            os.chdir(cur_dir)

    def run(self, *args: str, from_cwd: Path | None = None) -> ToxRunOutcome:
        with self.chdir(from_cwd):
            state = None
            self._capfd.readouterr()  # start with a clean state - drain
            code = None
            state = None

            def our_setup_state(value: Sequence[str]) -> State:
                nonlocal state
                state = previous_setup_state(value)
                return state

            with self.monkeypatch.context() as m:
                m.setattr(tox_env_api, "_CWD", self.path)
                m.setattr(tox.run, "setup_state", our_setup_state)
                m.setattr(sys, "argv", [sys.executable, "-m", "tox", *list(args)])
                m.setenv("VIRTUALENV_SYMLINK_APP_DATA", "1")
                m.setenv("VIRTUALENV_SYMLINKS", "1")
                m.setenv("VIRTUALENV_PIP", "embed")
                m.setenv("VIRTUALENV_WHEEL", "embed")
                m.setenv("VIRTUALENV_SETUPTOOLS", "embed")
                try:
                    tox_run(args)
                except SystemExit as exception:
                    code = exception.code
                if code is None:  # pragma: no branch
                    msg = "exit code not set"
                    raise RuntimeError(msg)
            out, err = self._capfd.readouterr()
            return ToxRunOutcome(args, self.path, cast(int, code), out, err, state)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(path={self.path}) at {id(self)}"


@pytest.fixture(autouse=True, scope="session")
def enable_pep517_backend_coverage() -> Iterator[None]:  # noqa: PT004
    try:
        import coverage  # noqa: F401
    except ImportError:  # pragma: no cover
        yield  # pragma: no cover
        return  # pragma: no cover
    # the COV_ env variables needs to be passed on for the PEP-517 backend
    from tox.tox_env.python.virtual_env.package.pyproject import Pep517VirtualEnvPackager

    def default_pass_env(self: Pep517VirtualEnvPackager) -> list[str]:
        result = previous(self)
        result.append("COV_*")
        return result

    previous = Pep517VirtualEnvPackager._default_pass_env  # noqa: SLF001
    try:
        Pep517VirtualEnvPackager._default_pass_env = default_pass_env  # type: ignore[assignment]  # noqa: SLF001
        yield
    finally:
        Pep517VirtualEnvPackager._default_pass_env = previous  # type: ignore[method-assign]  # noqa: SLF001


class ToxRunOutcome:
    def __init__(  # noqa: PLR0913
        self,
        cmd: Sequence[str],
        cwd: Path,
        code: int,
        out: str,
        err: str,
        state: State | None,
    ) -> None:
        extended_cmd = [sys.executable, "-m", "tox"]
        extended_cmd.extend(cmd)
        self.cmd: list[str] = extended_cmd
        self.cwd: Path = cwd
        self.code: int = code
        self.out: str = out
        self.err: str = err
        self._state: State | None = state

    @property
    def state(self) -> State:
        if self._state is None:
            msg = "no state"
            raise RuntimeError(msg)
        return self._state

    def env_conf(self, name: str) -> EnvConfigSet:
        return self.state.conf.get_env(name)

    @property
    def success(self) -> bool:
        return self.code == Outcome.OK

    def assert_success(self) -> None:
        assert self.success, repr(self)  # noqa: S101

    def assert_failed(self, code: int | None = None) -> None:
        status_match = self.code != 0 if code is None else self.code == code
        assert status_match, f"should be {code}, got {self}"  # noqa: S101

    def __repr__(self) -> str:
        return "\n".join(
            "{}{}{}".format(k, "\n" if "\n" in v else ": ", v)
            for k, v in (
                ("code", str(self.code)),
                ("cmd", self.shell_cmd),
                ("cwd", str(self.cwd)),
                ("standard output", self.out),
                ("standard error", self.err),
            )
            if v
        )

    @property
    def shell_cmd(self) -> str:
        return shell_cmd(self.cmd)

    def assert_out_err(self, out: str, err: str, *, dedent: bool = True, regex: bool = False) -> None:
        if dedent:
            out = textwrap.dedent(out).lstrip()
        if regex:
            self.matches(out, self.out, re.MULTILINE | re.DOTALL)
        else:
            assert self.out == out  # noqa: S101
        if dedent:
            err = textwrap.dedent(err).lstrip()
        if regex:
            self.matches(err, self.err, re.MULTILINE | re.DOTALL)
        else:
            assert self.err == err  # noqa: S101

    @staticmethod
    def matches(pattern: str, text: str, flags: int = 0) -> None:
        try:
            from re_assert import Matches
        except ImportError:  # pragma: no cover # hard to test
            match = re.match(pattern, text, flags)
            if match is None:
                warnings.warn("install the re-assert PyPI package for bette error message", UserWarning, stacklevel=1)
            assert match  # noqa: S101
        else:
            assert Matches(pattern, flags=flags) == text  # noqa: S101


class ToxProjectCreator(Protocol):
    def __call__(
        self,
        files: dict[str, Any],
        base: Path | None = None,
        prj_path: Path | None = None,
    ) -> ToxProject:
        ...


@pytest.fixture(name="tox_project")
def init_fixture(
    tmp_path: Path,
    capfd: CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> ToxProjectCreator:
    def _init(files: dict[str, Any], base: Path | None = None, prj_path: Path | None = None) -> ToxProject:
        """Create tox  projects."""
        return ToxProject(files, base, prj_path or tmp_path / "p", capfd, monkeypatch, mocker)

    return _init


@pytest.fixture()
def empty_project(tox_project: ToxProjectCreator, monkeypatch: pytest.MonkeyPatch) -> ToxProject:
    project = tox_project({"tox.ini": ""})
    monkeypatch.chdir(project.path)
    return project


_RUN_INTEGRATION_TEST_FLAG = "--run-integration"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(_RUN_INTEGRATION_TEST_FLAG, action="store_true", help="run the integration tests")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration")
    config.addinivalue_line("markers", "plugin_test")


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Function]) -> None:
    # do not require flags if called directly
    if len(items) == 1:  # pragma: no cover # hard to test
        return

    skip_int = pytest.mark.skip(reason=f"integration tests not run (no {_RUN_INTEGRATION_TEST_FLAG} flag)")

    def is_integration(test_item: pytest.Function) -> bool:
        return test_item.get_closest_marker("integration") is not None

    integration_enabled = config.getoption(_RUN_INTEGRATION_TEST_FLAG)
    if not integration_enabled:  # pragma: no cover # hard to test
        for item in items:
            if is_integration(item):
                item.add_marker(skip_int)
    # run integration tests (is_integration is True) after unit tests (False)
    items.sort(key=is_integration)


def enable_pypi_server(monkeypatch: pytest.MonkeyPatch, url: str | None) -> None:
    if url is None:  # pragma: no cover # only one of the branches can be hit depending on env
        monkeypatch.delenv("PIP_INDEX_URL", raising=False)
    else:  # pragma: no cover
        monkeypatch.setenv("PIP_INDEX_URL", url)
    monkeypatch.setenv("PIP_RETRIES", str(5))
    monkeypatch.setenv("PIP_TIMEOUT", str(2))


@pytest.fixture(scope="session")
def pypi_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[IndexServer]:
    # takes around 2.5s
    path = tmp_path_factory.mktemp("pypi")
    with IndexServer(path) as server:
        server.create_index("empty", "volatile=False")
        yield server


@pytest.fixture(scope="session")
def _invalid_index_fake_port() -> int:  # noqa: PT005
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as socket_handler:
        socket_handler.bind(("", 0))
        return cast(int, socket_handler.getsockname()[1])


@pytest.fixture(autouse=True)
def disable_pip_pypi_access(_invalid_index_fake_port: int, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str | None]:
    """Set a fake pip index url, tests that want to use a pypi server should create and overwrite this."""
    previous_url = os.environ.get("PIP_INDEX_URL")
    new_url = f"http://localhost:{_invalid_index_fake_port}/bad-pypi-server"
    monkeypatch.setenv("PIP_INDEX_URL", new_url)
    monkeypatch.setenv("PIP_RETRIES", str(0))
    monkeypatch.setenv("PIP_TIMEOUT", str(0.001))
    return new_url, previous_url


@pytest.fixture(name="enable_pip_pypi_access")
def enable_pip_pypi_access_fixture(
    disable_pip_pypi_access: tuple[str, str | None],
    monkeypatch: pytest.MonkeyPatch,
) -> str | None:
    """Set a fake pip index url, tests that want to use a pypi server should create and overwrite this."""
    _, previous_url = disable_pip_pypi_access
    enable_pypi_server(monkeypatch, previous_url)
    return previous_url


def register_inline_plugin(mocker: MockerFixture, *args: Callable[..., Any]) -> None:
    frame_info = inspect.stack()[1]
    caller_module = inspect.getmodule(frame_info[0])
    assert caller_module is not None  # noqa: S101
    plugin = ModuleType(f"{caller_module.__name__}|{frame_info[3]}")
    plugin.__file__ = caller_module.__file__
    plugin.__dict__.update({f.__name__: f for f in args})
    mocker.patch("tox.plugin.manager.load_inline", return_value=plugin)


LogCaptureFixture = pytest.LogCaptureFixture
TempPathFactory = pytest.TempPathFactory
MonkeyPatch = pytest.MonkeyPatch

__all__ = (
    "CaptureFixture",
    "LogCaptureFixture",
    "TempPathFactory",
    "MonkeyPatch",
    "SubRequest",
    "ToxRunOutcome",
    "ToxProject",
    "ToxProjectCreator",
    "check_os_environ",
    "register_inline_plugin",
)
