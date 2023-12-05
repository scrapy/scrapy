"""A tox environment that can build packages."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from threading import RLock
from types import MethodType
from typing import TYPE_CHECKING, Any, Callable, Generator, Iterator, cast

from filelock import FileLock

from .api import ToxEnv, ToxEnvCreateArgs

if TYPE_CHECKING:
    from tox.config.main import Config
    from tox.config.sets import EnvConfigSet

    from .runner import RunToxEnv


class Package:
    """package."""


class PathPackage(Package):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    def __str__(self) -> str:
        return str(self.path)


locked = False


def _lock_method(thread_lock: RLock, file_lock: FileLock | None, meth: Callable[..., Any]) -> Callable[..., Any]:
    def _func(*args: Any, **kwargs: Any) -> Any:
        with thread_lock:
            file_locks = False
            if file_lock is not None and file_lock.is_locked is False:  # file_lock is to lock from other tox processes
                file_lock.acquire()
                file_locks = True
            try:
                return meth(*args, **kwargs)
            finally:
                if file_locks:
                    cast(FileLock, file_lock).release()

    return _func


class PackageToxEnv(ToxEnv, ABC):
    def __init__(self, create_args: ToxEnvCreateArgs) -> None:
        self._thread_lock = RLock()
        self._file_lock: FileLock | None = None
        super().__init__(create_args)
        self._envs: set[str] = set()

    def __getattribute__(self, name: str) -> Any:
        # the packaging class might be used by multiple environments in parallel, hold a lock for operations on it
        obj = object.__getattribute__(self, name)
        if isinstance(obj, MethodType):
            obj = _lock_method(self._thread_lock, self._file_lock, obj)
        return obj

    def register_config(self) -> None:
        super().register_config()
        file_lock_path: Path = self.conf["env_dir"] / "file.lock"
        self._file_lock = FileLock(file_lock_path)
        file_lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.core.add_config(
            keys=["package_root", "setupdir"],
            of_type=Path,
            default=cast(Path, self.core["tox_root"]),
            desc="indicates where the packaging root file exists (historically setup.py file or pyproject.toml now)",
        )
        self.conf.add_config(
            keys=["package_root", "setupdir"],
            of_type=Path,
            default=cast(Path, self.core["package_root"]),
            desc="indicates where the packaging root file exists (historically setup.py file or pyproject.toml now)",
        )

    def _recreate_default(self, conf: Config, value: str | None) -> bool:
        return self.options.no_recreate_pkg is False and super()._recreate_default(conf, value)

    @abstractmethod
    def perform_packaging(self, for_env: EnvConfigSet) -> list[Package]:
        raise NotImplementedError

    def register_run_env(self, run_env: RunToxEnv) -> Generator[tuple[str, str], PackageToxEnv, None]:  # noqa: ARG002
        yield from ()  # empty generator by default

    def mark_active_run_env(self, run_env: RunToxEnv) -> None:
        self._envs.add(run_env.conf.name)

    def teardown_env(self, conf: EnvConfigSet) -> None:
        self._envs.remove(conf.name)
        if len(self._envs) == 0:
            self._teardown()

    @abstractmethod
    def child_pkg_envs(self, run_conf: EnvConfigSet) -> Iterator[PackageToxEnv]:
        raise NotImplementedError
