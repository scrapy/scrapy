from __future__ import annotations

import logging
import os
import sys
from collections import defaultdict
from contextlib import contextmanager
from itertools import chain
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any, Dict, Generator, Iterator, Literal, NoReturn, Optional, Sequence, cast

from cachetools import cached
from packaging.requirements import Requirement
from pyproject_api import (
    BackendFailed,
    CmdStatus,
    Frontend,
    MetadataForBuildEditableResult,
    MetadataForBuildWheelResult,
)

from tox.execute.pep517_backend import LocalSubProcessPep517Executor
from tox.execute.request import StdinSource
from tox.plugin import impl
from tox.tox_env.errors import Fail
from tox.tox_env.python.package import (
    EditableLegacyPackage,
    EditablePackage,
    PythonPackageToxEnv,
    SdistPackage,
    WheelPackage,
)
from tox.tox_env.python.virtual_env.api import VirtualEnv
from tox.util.file_view import create_session_view

from .util import dependencies_with_extras, dependencies_with_extras_from_markers

if TYPE_CHECKING:
    from tox.config.sets import EnvConfigSet
    from tox.execute.api import ExecuteStatus
    from tox.tox_env.api import ToxEnvCreateArgs
    from tox.tox_env.package import Package, PackageToxEnv
    from tox.tox_env.register import ToxEnvRegister
    from tox.tox_env.runner import RunToxEnv

from importlib.metadata import Distribution, PathDistribution

if sys.version_info >= (3, 11):  # pragma: no cover (py311+)
    import tomllib
else:  # pragma: no cover (py311+)
    import tomli as tomllib

ConfigSettings = Optional[Dict[str, Any]]


class ToxBackendFailed(Fail, BackendFailed):
    def __init__(self, backend_failed: BackendFailed) -> None:
        Fail.__init__(self)
        result: dict[str, Any] = {
            "code": backend_failed.code,
            "exc_type": backend_failed.exc_type,
            "exc_msg": backend_failed.exc_msg,
        }
        BackendFailed.__init__(
            self,
            result,
            backend_failed.out,
            backend_failed.err,
        )


class BuildEditableNotSupportedError(RuntimeError):
    """raised when build editable is not supported."""


class ToxCmdStatus(CmdStatus):
    def __init__(self, execute_status: ExecuteStatus) -> None:
        self._execute_status = execute_status

    @property
    def done(self) -> bool:
        # 1. process died
        status = self._execute_status
        if status.exit_code is not None:  # pragma: no branch
            return True  # pragma: no cover
        # 2. the backend output reported back that our command is done
        return b"\n" in status.out.rpartition(b"Backend: Wrote response ")[0]

    def out_err(self) -> tuple[str, str]:
        status = self._execute_status
        if status is None or status.outcome is None:  # interrupt before status create # pragma: no branch
            return "", ""  # pragma: no cover
        return status.outcome.out_err()


class Pep517VirtualEnvPackager(PythonPackageToxEnv, VirtualEnv):
    """local file system python virtual environment via the virtualenv package."""

    def __init__(self, create_args: ToxEnvCreateArgs) -> None:
        super().__init__(create_args)
        self._frontend_: Pep517VirtualEnvFrontend | None = None
        self.builds: defaultdict[str, list[EnvConfigSet]] = defaultdict(list)
        self.call_require_hooks: set[str] = set()
        self._distribution_meta: PathDistribution | None = None
        self._package_dependencies: list[Requirement] | None = None
        self._package_name: str | None = None
        self._pkg_lock = RLock()  # can build only one package at a time
        self.root = self.conf["package_root"]
        self._package_paths: set[Path] = set()

    @staticmethod
    def id() -> str:  # noqa: A003
        return "virtualenv-pep-517"

    @property
    def _frontend(self) -> Pep517VirtualEnvFrontend:
        if self._frontend_ is None:
            self._frontend_ = Pep517VirtualEnvFrontend(self.root, self)
        return self._frontend_

    def register_config(self) -> None:
        super().register_config()
        self.conf.add_config(
            keys=["meta_dir"],
            of_type=Path,
            default=lambda conf, name: self.env_dir / ".meta",  # noqa: ARG005
            desc="directory where to put the project metadata files",
        )
        self.conf.add_config(
            keys=["pkg_dir"],
            of_type=Path,
            default=lambda conf, name: self.env_dir / "dist",  # noqa: ARG005
            desc="directory where to put project packages",
        )
        for key in ("sdist", "wheel", "editable"):
            self._add_config_settings(key)

    def _add_config_settings(self, build_type: str) -> None:
        # config settings passed to PEP-517-compliant build backend https://peps.python.org/pep-0517/#config-settings
        keys = {
            "sdist": ["get_requires_for_build_sdist", "build_sdist"],
            "wheel": ["get_requires_for_build_wheel", "prepare_metadata_for_build_wheel", "build_wheel"],
            "editable": ["get_requires_for_build_editable", "prepare_metadata_for_build_editable", "build_editable"],
        }
        for key in keys.get(build_type, []):
            self.conf.add_config(
                keys=[f"config_settings_{key}"],
                of_type=Dict[str, str],
                default=None,  # type: ignore[arg-type]
                desc=f"config settings passed to the {key} backend API endpoint",
            )

    @property
    def pkg_dir(self) -> Path:
        return cast(Path, self.conf["pkg_dir"])

    @property
    def meta_folder(self) -> Path:
        meta_folder: Path = self.conf["meta_dir"]
        meta_folder.mkdir(exist_ok=True)
        return meta_folder

    @property
    def meta_folder_if_populated(self) -> Path | None:
        """Return the metadata directory if it contains any files, otherwise None."""
        meta_folder = self.meta_folder
        if meta_folder.exists() and tuple(meta_folder.iterdir()):
            return meta_folder
        return None

    def register_run_env(self, run_env: RunToxEnv) -> Generator[tuple[str, str], PackageToxEnv, None]:
        yield from super().register_run_env(run_env)
        build_type = run_env.conf["package"]
        self.call_require_hooks.add(build_type)
        self.builds[build_type].append(run_env.conf)

    def _setup_env(self) -> None:
        super()._setup_env()
        if "sdist" in self.call_require_hooks or "external" in self.call_require_hooks:
            self._setup_build_requires("sdist")
        if "wheel" in self.call_require_hooks:
            self._setup_build_requires("wheel")
        if "editable" in self.call_require_hooks:
            if not self._frontend.optional_hooks["build_editable"]:
                raise BuildEditableNotSupportedError
            self._setup_build_requires("editable")

    def _setup_build_requires(self, of_type: str) -> None:
        settings: ConfigSettings = self.conf[f"config_settings_get_requires_for_build_{of_type}"]
        requires = getattr(self._frontend, f"get_requires_for_build_{of_type}")(config_settings=settings).requires
        self._install(requires, PythonPackageToxEnv.__name__, f"requires_for_build_{of_type}")

    def _teardown(self) -> None:
        executor = self._frontend.backend_executor
        if executor is not None:  # pragma: no branch
            try:
                if executor.is_alive:
                    self._frontend._send("_exit")  # try first on amicable shutdown  # noqa: SLF001
            except SystemExit:  # pragma: no cover  # if already has been interrupted ignore
                pass
            finally:
                executor.close()
        for path in self._package_paths:
            if path.exists():
                logging.debug("delete package %s", path)
                path.unlink()
        super()._teardown()

    def perform_packaging(self, for_env: EnvConfigSet) -> list[Package]:
        """Build the package to install."""
        try:
            deps = self._load_deps(for_env)
        except BuildEditableNotSupportedError:
            self.call_require_hooks.remove("editable")
            targets = [e for e in self.builds.pop("editable") if e["package"] == "editable"]
            names = ", ".join(sorted({t.env_name for t in targets if t.env_name}))

            logging.error(  # noqa: TRY400
                "package config for %s is editable, however the build backend %s does not support PEP-660, falling "
                "back to editable-legacy - change your configuration to it",
                names,
                cast(Pep517VirtualEnvFrontend, self._frontend_).backend,
            )
            for env in targets:
                env._defined["package"].value = "editable-legacy"  # type: ignore[attr-defined]  # noqa: SLF001
                self.builds["editable-legacy"].append(env)
            self._run_state["setup"] = False  # force setup again as we need to provision wheel to get dependencies
            deps = self._load_deps(for_env)
        of_type: str = for_env["package"]
        if of_type == "editable-legacy":
            self.setup()
            config_settings: ConfigSettings = self.conf["config_settings_get_requires_for_build_sdist"]
            sdist_requires = self._frontend.get_requires_for_build_sdist(config_settings=config_settings).requires
            deps = [*self.requires(), *sdist_requires, *deps]
            package: Package = EditableLegacyPackage(self.core["tox_root"], deps)  # the folder itself is the package
        elif of_type == "sdist":
            self.setup()
            with self._pkg_lock:
                config_settings = self.conf["config_settings_build_sdist"]
                sdist = self._frontend.build_sdist(sdist_directory=self.pkg_dir, config_settings=config_settings).sdist
                sdist = create_session_view(sdist, self._package_temp_path)
                self._package_paths.add(sdist)
                package = SdistPackage(sdist, deps)
        elif of_type in {"wheel", "editable"}:
            w_env = self._wheel_build_envs.get(for_env["wheel_build_env"])
            if w_env is not None and w_env is not self:
                with w_env.display_context(self._has_display_suspended):
                    return w_env.perform_packaging(for_env)
            else:
                self.setup()
                method = "build_editable" if of_type == "editable" else "build_wheel"
                config_settings = self.conf[f"config_settings_{method}"]
                with self._pkg_lock:
                    wheel = getattr(self._frontend, method)(
                        wheel_directory=self.pkg_dir,
                        metadata_directory=self.meta_folder_if_populated,
                        config_settings=config_settings,
                    ).wheel
                    wheel = create_session_view(wheel, self._package_temp_path)
                    self._package_paths.add(wheel)
                package = (EditablePackage if of_type == "editable" else WheelPackage)(wheel, deps)
        else:  # pragma: no cover # for when we introduce new packaging types and don't implement
            msg = f"cannot handle package type {of_type}"
            raise TypeError(msg)  # pragma: no cover
        return [package]

    @property
    def _package_temp_path(self) -> Path:
        return cast(Path, self.core["temp_dir"]) / "package"

    def _load_deps(self, for_env: EnvConfigSet) -> list[Requirement]:
        # first check if this is statically available via PEP-621
        deps = self._load_deps_from_static(for_env)
        if deps is None:
            deps = self._load_deps_from_built_metadata(for_env)
        return deps

    def _load_deps_from_static(self, for_env: EnvConfigSet) -> list[Requirement] | None:
        pyproject_file = self.core["package_root"] / "pyproject.toml"
        if not pyproject_file.exists():  # check if it's static PEP-621 metadata
            return None
        with pyproject_file.open("rb") as file_handler:
            pyproject = tomllib.load(file_handler)
        if "project" not in pyproject:
            return None  # is not a PEP-621 pyproject
        project = pyproject["project"]
        extras: set[str] = for_env["extras"]
        for dynamic in project.get("dynamic", []):
            if dynamic == "dependencies" or (extras and dynamic == "optional-dependencies"):
                return None  # if any dependencies are dynamic we can just calculate all dynamically

        deps_with_markers: list[tuple[Requirement, set[str | None]]] = [
            (Requirement(i), {None}) for i in project.get("dependencies", [])
        ]
        optional_deps = project.get("optional-dependencies", {})
        for extra, reqs in optional_deps.items():
            deps_with_markers.extend((Requirement(req), {extra}) for req in (reqs or []))
        return dependencies_with_extras_from_markers(
            deps_with_markers=deps_with_markers,
            extras=extras,
            package_name=project.get("name", "."),
        )

    def _load_deps_from_built_metadata(self, for_env: EnvConfigSet) -> list[Requirement]:
        # dependencies might depend on the python environment we're running in => if we build a wheel use that env
        # to calculate the package metadata, otherwise ourselves
        of_type: str = for_env["package"]
        reqs: list[Requirement] | None = None
        name = ""
        if of_type in ("wheel", "editable"):  # wheel packages
            w_env = self._wheel_build_envs.get(for_env["wheel_build_env"])
            if w_env is not None and w_env is not self:
                with w_env.display_context(self._has_display_suspended):
                    if isinstance(w_env, Pep517VirtualEnvPackager):
                        reqs, name = w_env.get_package_dependencies(for_env), w_env.get_package_name(for_env)
                    else:
                        reqs = []
        if reqs is None:
            reqs = self.get_package_dependencies(for_env)
            name = self.get_package_name(for_env)
        extras: set[str] = for_env["extras"]
        return dependencies_with_extras(reqs, extras, name)

    def get_package_dependencies(self, for_env: EnvConfigSet) -> list[Requirement]:
        with self._pkg_lock:
            if self._package_dependencies is None:  # pragma: no branch
                self._ensure_meta_present(for_env)
                requires: list[str] = cast(PathDistribution, self._distribution_meta).requires or []
                self._package_dependencies = [Requirement(i) for i in requires]  # pragma: no branch
        return self._package_dependencies

    def get_package_name(self, for_env: EnvConfigSet) -> str:
        with self._pkg_lock:
            if self._package_name is None:  # pragma: no branch
                self._ensure_meta_present(for_env)
                self._package_name = cast(PathDistribution, self._distribution_meta).metadata["Name"]
        return self._package_name

    def _ensure_meta_present(self, for_env: EnvConfigSet) -> None:
        if self._distribution_meta is not None:  # pragma: no branch
            return  # pragma: no cover
        # even if we don't build a wheel we need the requirements for it should we want to build its metadata
        target: Literal["editable", "wheel"] = "editable" if for_env["package"] == "editable" else "wheel"
        self.call_require_hooks.add(target)

        self.setup()
        hook = getattr(self._frontend, f"prepare_metadata_for_build_{target}")
        config: ConfigSettings = self.conf[f"config_settings_prepare_metadata_for_build_{target}"]
        result: MetadataForBuildWheelResult | MetadataForBuildEditableResult | None = hook(self.meta_folder, config)
        if result is None:
            config = self.conf[f"config_settings_build_{target}"]
            dist_info_path, _, __ = self._frontend.metadata_from_built(self.meta_folder, target, config)
            dist_info = str(dist_info_path)
        else:
            dist_info = str(result.metadata)
        self._distribution_meta = Distribution.at(dist_info)

    def requires(self) -> tuple[Requirement, ...]:
        return self._frontend.requires


class Pep517VirtualEnvFrontend(Frontend):
    def __init__(self, root: Path, env: Pep517VirtualEnvPackager) -> None:
        super().__init__(*Frontend.create_args_from_folder(root))
        self._tox_env = env
        self._backend_executor_: LocalSubProcessPep517Executor | None = None
        into: dict[str, Any] = {}

        for hook in chain(
            (f"get_requires_for_build_{build_type}" for build_type in ["editable", "wheel", "sdist"]),
            (f"prepare_metadata_for_build_{build_type}" for build_type in ["editable", "wheel"]),
            (f"build_{build_type}" for build_type in ["editable", "wheel", "sdist"]),
        ):  # wrap build methods in a cache wrapper

            def key(*args: Any, bound_return: str = hook, **kwargs: Any) -> str:  # noqa: ARG001
                return bound_return

            setattr(self, hook, cached(into, key=key)(getattr(self, hook)))

    @property
    def backend_cmd(self) -> Sequence[str]:
        return ["python", *self.backend_args]

    def _send(self, cmd: str, **kwargs: Any) -> tuple[Any, str, str]:
        try:
            if self._can_skip_prepare(cmd):
                return None, "", ""  # will need to build wheel either way, avoid prepare
            return super()._send(cmd, **kwargs)
        except BackendFailed as exception:
            raise exception if isinstance(exception, ToxBackendFailed) else ToxBackendFailed(exception) from exception

    def _can_skip_prepare(self, cmd: str) -> bool:
        # given we'll build a wheel we might skip the prepare step
        return cmd in ("prepare_metadata_for_build_wheel", "prepare_metadata_for_build_editable") and (
            "wheel" in self._tox_env.builds or "editable" in self._tox_env.builds
        )

    @contextmanager
    def _send_msg(
        self,
        cmd: str,
        result_file: Path,  # noqa: ARG002
        msg: str,
    ) -> Iterator[ToxCmdStatus]:
        with self._tox_env.execute_async(
            cmd=self.backend_cmd,
            cwd=self._root,
            stdin=StdinSource.API,
            show=None,
            run_id=cmd,
            executor=self.backend_executor,
        ) as execute_status:
            execute_status.write_stdin(f"{msg}{os.linesep}")
            yield ToxCmdStatus(execute_status)
        outcome = execute_status.outcome
        if outcome is not None:  # pragma: no branch
            outcome.assert_success()

    def _unexpected_response(  # noqa: PLR0913
        self,
        cmd: str,
        got: Any,
        expected_type: Any,
        out: str,
        err: str,
    ) -> NoReturn:
        try:
            super()._unexpected_response(cmd, got, expected_type, out, err)
        except BackendFailed as exception:
            raise exception if isinstance(exception, ToxBackendFailed) else ToxBackendFailed(exception) from exception

    @property
    def backend_executor(self) -> LocalSubProcessPep517Executor:
        if self._backend_executor_ is None:
            environment_variables = self._tox_env.environment_variables.copy()
            backend = os.pathsep.join(str(i) for i in self._backend_paths).strip()
            if backend:
                environment_variables["PYTHONPATH"] = backend
            self._backend_executor_ = LocalSubProcessPep517Executor(
                colored=self._tox_env.options.is_colored,
                cmd=self.backend_cmd,
                env=environment_variables,
                cwd=self._root,
            )

        return self._backend_executor_

    @contextmanager
    def _wheel_directory(self) -> Iterator[Path]:
        yield self._tox_env.pkg_dir  # use our local wheel directory for building wheel


@impl
def tox_register_tox_env(register: ToxEnvRegister) -> None:
    register.add_package_env(Pep517VirtualEnvPackager)
