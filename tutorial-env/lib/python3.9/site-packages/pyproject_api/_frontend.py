"""Build frontend for PEP-517."""
from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from time import sleep
from typing import Any, Dict, Iterator, List, Literal, NamedTuple, NoReturn, Optional, TypedDict, cast
from zipfile import ZipFile

from packaging.requirements import Requirement

from pyproject_api._util import ensure_empty_dir

if sys.version_info >= (3, 11):  # pragma: no cover (py311+)
    import tomllib
else:  # pragma: no cover (py311+)
    import tomli as tomllib

_HERE = Path(__file__).parent
ConfigSettings = Optional[Dict[str, Any]]


class OptionalHooks(TypedDict, total=True):
    """A flag indicating if the backend supports the optional hook or not."""

    get_requires_for_build_sdist: bool
    prepare_metadata_for_build_wheel: bool
    get_requires_for_build_wheel: bool
    build_editable: bool
    get_requires_for_build_editable: bool
    prepare_metadata_for_build_editable: bool


class CmdStatus(ABC):
    @property
    @abstractmethod
    def done(self) -> bool:
        """:return: truthful when the command finished running"""
        raise NotImplementedError

    @abstractmethod
    def out_err(self) -> tuple[str, str]:
        """:return: standard output and standard error text"""
        raise NotImplementedError


class RequiresBuildSdistResult(NamedTuple):
    """Information collected while acquiring the source distribution build dependencies."""

    #: wheel build dependencies
    requires: tuple[Requirement, ...]
    #: backend standard output while acquiring the source distribution build dependencies
    out: str
    #: backend standard output while acquiring the source distribution build dependencies
    err: str


class RequiresBuildWheelResult(NamedTuple):
    """Information collected while acquiring the wheel build dependencies."""

    #: wheel build dependencies
    requires: tuple[Requirement, ...]
    #: backend standard output while acquiring the wheel build dependencies
    out: str
    #: backend standard error while acquiring the wheel build dependencies
    err: str


class RequiresBuildEditableResult(NamedTuple):
    """Information collected while acquiring the wheel build dependencies."""

    #: editable wheel build dependencies
    requires: tuple[Requirement, ...]
    #: backend standard output while acquiring the editable wheel build dependencies
    out: str
    #: backend standard error while acquiring the editable wheel build dependencies
    err: str


class MetadataForBuildWheelResult(NamedTuple):
    """Information collected while acquiring the wheel metadata."""

    #: path to the wheel metadata
    metadata: Path
    #: backend standard output while generating the wheel metadata
    out: str
    #: backend standard output while generating the wheel metadata
    err: str


class MetadataForBuildEditableResult(NamedTuple):
    """Information collected while acquiring the editable metadata."""

    #: path to the wheel metadata
    metadata: Path
    #: backend standard output while generating the editable wheel metadata
    out: str
    #: backend standard output while generating the editable wheel metadata
    err: str


class SdistResult(NamedTuple):
    """Information collected while building a source distribution."""

    #: path to the built source distribution
    sdist: Path
    #: backend standard output while building the source distribution
    out: str
    #: backend standard output while building the source distribution
    err: str


class WheelResult(NamedTuple):
    """Information collected while building a wheel."""

    #: path to the built wheel artifact
    wheel: Path
    #: backend standard output while building the wheel
    out: str
    #: backend standard error while building the wheel
    err: str


class EditableResult(NamedTuple):
    """Information collected while building an editable wheel."""

    #: path to the built wheel artifact
    wheel: Path
    #: backend standard output while building the wheel
    out: str
    #: backend standard error while building the wheel
    err: str


class BackendFailed(RuntimeError):  # noqa: N818
    """An error of the build backend."""

    def __init__(self, result: dict[str, Any], out: str, err: str) -> None:
        super().__init__()
        #: standard output collected while running the command
        self.out = out
        #: standard error collected while running the command
        self.err = err
        #: exit code of the command
        self.code: int = result.get("code", -2)
        #: the type of exception thrown
        self.exc_type: str = result.get("exc_type", "missing Exception type")
        #: the string representation of the exception thrown
        self.exc_msg: str = result.get("exc_msg", "missing Exception message")

    def __str__(self) -> str:
        return (
            f"packaging backend failed{'' if self.code is None else f' (code={self.code})'}, "
            f"with {self.exc_type}: {self.exc_msg}\n{self.err}{self.out}"
        ).rstrip()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"result=dict(code={self.code}, exc_type={self.exc_type!r},exc_msg={self.exc_msg!r}),"
            f" out={self.out!r}, err={self.err!r})"
        )


class Frontend(ABC):
    """Abstract base class for a pyproject frontend."""

    #: backend key when the ``pyproject.toml`` does not specify it
    LEGACY_BUILD_BACKEND: str = "setuptools.build_meta:__legacy__"
    #: backend requirements when the ``pyproject.toml`` does not specify it
    LEGACY_REQUIRES: tuple[Requirement, ...] = (Requirement("setuptools >= 40.8.0"), Requirement("wheel"))

    def __init__(  # noqa: PLR0913
        self,
        root: Path,
        backend_paths: tuple[Path, ...],
        backend_module: str,
        backend_obj: str | None,
        requires: tuple[Requirement, ...],
        reuse_backend: bool = True,  # noqa: FBT001, FBT002
    ) -> None:
        """
        Create a new frontend.

        :param root: the root path of the project
        :param backend_paths: paths to provision as available to import from for the build backend
        :param backend_module: the module where the backend lives
        :param backend_obj: the backend object key (will be lookup up within the backend module)
        :param requires: build requirements for the backend
        :param reuse_backend: a flag indicating if the communication channel should be kept alive between messages
        """
        self._root = root
        self._backend_paths = backend_paths
        self._backend_module = backend_module
        self._backend_obj = backend_obj
        self.requires: tuple[Requirement, ...] = requires
        self._reuse_backend = reuse_backend
        self._optional_hooks: OptionalHooks | None = None

    @classmethod
    def create_args_from_folder(
        cls,
        folder: Path,
    ) -> tuple[Path, tuple[Path, ...], str, str | None, tuple[Requirement, ...], bool]:
        """
        Frontend creation arguments from a python project folder (thould have a ``pypyproject.toml`` file per PEP-518).

        :param folder: the python project folder
        :return: the frontend creation args

        E.g., to create a frontend from a python project folder:

        .. code:: python

            frontend = Frontend(*Frontend.create_args_from_folder(project_folder))
        """
        py_project_toml = folder / "pyproject.toml"
        if py_project_toml.exists():
            with py_project_toml.open("rb") as file_handler:
                py_project = tomllib.load(file_handler)
            build_system = py_project.get("build-system", {})
            if "backend-path" in build_system:
                backend_paths: tuple[Path, ...] = tuple(folder / p for p in build_system["backend-path"])
            else:
                backend_paths = ()
            if "requires" in build_system:
                requires: tuple[Requirement, ...] = tuple(Requirement(r) for r in build_system.get("requires"))
            else:
                requires = cls.LEGACY_REQUIRES
            build_backend = build_system.get("build-backend", cls.LEGACY_BUILD_BACKEND)
        else:
            backend_paths = ()
            requires = cls.LEGACY_REQUIRES
            build_backend = cls.LEGACY_BUILD_BACKEND
        paths = build_backend.split(":")
        backend_module: str = paths[0]
        backend_obj: str | None = paths[1] if len(paths) > 1 else None
        return folder, backend_paths, backend_module, backend_obj, requires, True

    @property
    def backend(self) -> str:
        """:return: backend key"""
        return f"{self._backend_module}{f':{self._backend_obj}' if self._backend_obj else ''}"

    @property
    def backend_args(self) -> list[str]:
        """:return: startup arguments for a backend"""
        result: list[str] = [str(_HERE / "_backend.py"), str(self._reuse_backend), self._backend_module]
        if self._backend_obj:
            result.append(self._backend_obj)
        return result

    @property
    def optional_hooks(self) -> OptionalHooks:
        """:return: a dictionary indicating if the optional hook is supported or not"""
        if self._optional_hooks is None:
            result, _, __ = self._send("_optional_hooks")
            self._optional_hooks = result
        return self._optional_hooks

    def get_requires_for_build_sdist(self, config_settings: ConfigSettings | None = None) -> RequiresBuildSdistResult:
        """
        Get build requirements for a source distribution (per PEP-517).

        :param config_settings: run arguments
        :return: outcome
        """
        if self.optional_hooks["get_requires_for_build_sdist"]:
            result, out, err = self._send(cmd="get_requires_for_build_sdist", config_settings=config_settings)
        else:
            result, out, err = [], "", ""
        if not isinstance(result, list) or not all(isinstance(i, str) for i in result):
            self._unexpected_response("get_requires_for_build_sdist", result, "list of string", out, err)
        return RequiresBuildSdistResult(tuple(Requirement(r) for r in cast(List[str], result)), out, err)

    def get_requires_for_build_wheel(self, config_settings: ConfigSettings | None = None) -> RequiresBuildWheelResult:
        """
        Get build requirements for a wheel (per PEP-517).

        :param config_settings: run arguments
        :return: outcome
        """
        if self.optional_hooks["get_requires_for_build_wheel"]:
            result, out, err = self._send(cmd="get_requires_for_build_wheel", config_settings=config_settings)
        else:
            result, out, err = [], "", ""
        if not isinstance(result, list) or not all(isinstance(i, str) for i in result):
            self._unexpected_response("get_requires_for_build_wheel", result, "list of string", out, err)
        return RequiresBuildWheelResult(tuple(Requirement(r) for r in cast(List[str], result)), out, err)

    def get_requires_for_build_editable(
        self,
        config_settings: ConfigSettings | None = None,
    ) -> RequiresBuildEditableResult:
        """
        Get build requirements for an editable wheel build (per PEP-660).

        :param config_settings: run arguments
        :return: outcome
        """
        if self.optional_hooks["get_requires_for_build_editable"]:
            result, out, err = self._send(cmd="get_requires_for_build_editable", config_settings=config_settings)
        else:
            result, out, err = [], "", ""
        if not isinstance(result, list) or not all(isinstance(i, str) for i in result):
            self._unexpected_response("get_requires_for_build_editable", result, "list of string", out, err)
        return RequiresBuildEditableResult(tuple(Requirement(r) for r in cast(List[str], result)), out, err)

    def prepare_metadata_for_build_wheel(
        self,
        metadata_directory: Path,
        config_settings: ConfigSettings | None = None,
    ) -> MetadataForBuildWheelResult | None:
        """
        Build wheel metadata (per PEP-517).

        :param metadata_directory: where to generate the metadata
        :param config_settings: build arguments
        :return: metadata generation result
        """
        self._check_metadata_dir(metadata_directory)
        basename: str | None = None
        if self.optional_hooks["prepare_metadata_for_build_wheel"]:
            basename, out, err = self._send(
                cmd="prepare_metadata_for_build_wheel",
                metadata_directory=metadata_directory,
                config_settings=config_settings,
            )
        if basename is None:
            return None
        if not isinstance(basename, str):
            self._unexpected_response("prepare_metadata_for_build_wheel", basename, str, out, err)
        return MetadataForBuildWheelResult(metadata_directory / basename, out, err)

    def _check_metadata_dir(self, metadata_directory: Path) -> None:
        if metadata_directory == self._root:
            msg = f"the project root and the metadata directory can't be the same {self._root}"
            raise RuntimeError(msg)
        if metadata_directory.exists():  # start with fresh
            ensure_empty_dir(metadata_directory)
        metadata_directory.mkdir(parents=True, exist_ok=True)

    def prepare_metadata_for_build_editable(
        self,
        metadata_directory: Path,
        config_settings: ConfigSettings | None = None,
    ) -> MetadataForBuildEditableResult | None:
        """
        Build editable wheel metadata (per PEP-660).

        :param metadata_directory: where to generate the metadata
        :param config_settings: build arguments
        :return: metadata generation result
        """
        self._check_metadata_dir(metadata_directory)
        basename: str | None = None
        if self.optional_hooks["prepare_metadata_for_build_editable"]:
            basename, out, err = self._send(
                cmd="prepare_metadata_for_build_editable",
                metadata_directory=metadata_directory,
                config_settings=config_settings,
            )
        if basename is None:
            return None
        if not isinstance(basename, str):
            self._unexpected_response("prepare_metadata_for_build_wheel", basename, str, out, err)
        result = metadata_directory / basename
        return MetadataForBuildEditableResult(result, out, err)

    def build_sdist(self, sdist_directory: Path, config_settings: ConfigSettings | None = None) -> SdistResult:
        """
        Build a source distribution (per PEP-517).

        :param sdist_directory: the folder where to build the source distribution
        :param config_settings: build arguments
        :return: source distribution build result
        """
        sdist_directory.mkdir(parents=True, exist_ok=True)
        basename, out, err = self._send(
            cmd="build_sdist",
            sdist_directory=sdist_directory,
            config_settings=config_settings,
        )
        if not isinstance(basename, str):
            self._unexpected_response("build_sdist", basename, str, out, err)
        return SdistResult(sdist_directory / basename, out, err)

    def build_wheel(
        self,
        wheel_directory: Path,
        config_settings: ConfigSettings | None = None,
        metadata_directory: Path | None = None,
    ) -> WheelResult:
        """
        Build a wheel file (per PEP-517).

        :param wheel_directory: the folder where to build the wheel
        :param config_settings: build arguments
        :param metadata_directory: wheel metadata folder
        :return: wheel build result
        """
        wheel_directory.mkdir(parents=True, exist_ok=True)
        basename, out, err = self._send(
            cmd="build_wheel",
            wheel_directory=wheel_directory,
            config_settings=config_settings,
            metadata_directory=metadata_directory,
        )
        if not isinstance(basename, str):
            self._unexpected_response("build_wheel", basename, str, out, err)
        return WheelResult(wheel_directory / basename, out, err)

    def build_editable(
        self,
        wheel_directory: Path,
        config_settings: ConfigSettings | None = None,
        metadata_directory: Path | None = None,
    ) -> EditableResult:
        """
        Build an editable wheel file (per PEP-660).

        :param wheel_directory: the folder where to build the editable wheel
        :param config_settings: build arguments
        :param metadata_directory: wheel metadata folder
        :return: wheel build result
        """
        wheel_directory.mkdir(parents=True, exist_ok=True)
        basename, out, err = self._send(
            cmd="build_editable",
            wheel_directory=wheel_directory,
            config_settings=config_settings,
            metadata_directory=metadata_directory,
        )
        if not isinstance(basename, str):
            self._unexpected_response("build_editable", basename, str, out, err)
        return EditableResult(wheel_directory / basename, out, err)

    def _unexpected_response(  # noqa: PLR0913
        self,
        cmd: str,
        got: Any,
        expected_type: Any,
        out: str,
        err: str,
    ) -> NoReturn:
        msg = f"{cmd!r} on {self.backend!r} returned {got!r} but expected type {expected_type!r}"
        raise BackendFailed({"code": None, "exc_type": TypeError.__name__, "exc_msg": msg}, out, err)

    def metadata_from_built(
        self,
        metadata_directory: Path,
        target: Literal["wheel", "editable"],
        config_settings: ConfigSettings | None = None,
    ) -> tuple[Path, str, str]:
        """
        Create metadata from building the wheel (use when the prepare endpoints are not present or don't work).

        :param metadata_directory: directory where to put the metadata
        :param target: the type of wheel metadata to build
        :param config_settings: config settings to pass in to the build endpoint
        :return:
        """
        hook = getattr(self, f"build_{target}")
        with self._wheel_directory() as wheel_directory:
            result: EditableResult | WheelResult = hook(wheel_directory, config_settings)
            wheel = result.wheel
            if not wheel.exists():
                msg = f"missing wheel file return by backed {wheel!r}"
                raise RuntimeError(msg)
            out, err = result.out, result.err
            extract_to = str(metadata_directory)
            basename = None
            with ZipFile(str(wheel), "r") as zip_file:
                for name in zip_file.namelist():  # pragma: no branch
                    root = Path(name).parts[0]
                    if root.endswith(".dist-info"):
                        basename = root
                        zip_file.extract(name, extract_to)
        if basename is None:  # pragma: no branch
            msg = f"no .dist-info found inside generated wheel {wheel}"
            raise RuntimeError(msg)
        return metadata_directory / basename, out, err

    @contextmanager
    def _wheel_directory(self) -> Iterator[Path]:
        with TemporaryDirectory() as wheel_directory:
            yield Path(wheel_directory)

    def _send(self, cmd: str, **kwargs: Any) -> tuple[Any, str, str]:
        with NamedTemporaryFile(prefix=f"pep517_{cmd}-") as result_file_marker:
            result_file = Path(result_file_marker.name).with_suffix(".json")
            msg = json.dumps(
                {
                    "cmd": cmd,
                    "kwargs": {k: (str(v) if isinstance(v, Path) else v) for k, v in kwargs.items()},
                    "result": str(result_file),
                },
            )
            with self._send_msg(cmd, result_file, msg) as status:
                while not status.done:  # pragma: no branch
                    sleep(0.001)  # wait a bit for things to happen
            if result_file.exists():
                try:
                    with result_file.open("rt") as result_handler:
                        result = json.load(result_handler)
                finally:
                    result_file.unlink()
            else:
                result = {
                    "code": 1,
                    "exc_type": "RuntimeError",
                    "exc_msg": f"Backend response file {result_file} is missing",
                }
        out, err = status.out_err()
        if "return" in result:
            return result["return"], out, err
        raise BackendFailed(result, out, err)

    @abstractmethod
    @contextmanager
    def _send_msg(self, cmd: str, result_file: Path, msg: str) -> Iterator[CmdStatus]:
        raise NotImplementedError
