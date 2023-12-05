from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod
from hashlib import sha256
from typing import TYPE_CHECKING, Any, Iterable, List

from tox.config.types import Command, EnvList

from .api import ToxEnv, ToxEnvCreateArgs
from .package import Package, PackageToxEnv, PathPackage
from .util import add_change_dir_conf

if TYPE_CHECKING:
    from tox.journal import EnvJournal


class RunToxEnv(ToxEnv, ABC):
    def __init__(self, create_args: ToxEnvCreateArgs) -> None:
        self.package_env: PackageToxEnv | None = None
        self._packages: list[Package] = []
        super().__init__(create_args)
        self._package_envs: list[PackageToxEnv | Exception] | None = None

    def register_config(self) -> None:
        def ensure_one_line(value: str) -> str:
            return re.sub(r"\s+", " ", value.replace("\r", "").replace("\n", " "))

        self.conf.add_config(
            keys=["description"],
            of_type=str,
            default="",
            desc="description attached to the tox environment",
            post_process=ensure_one_line,
        )
        self.conf.add_config(
            "depends",
            of_type=EnvList,
            desc="tox environments that this environment depends on (must be run after those)",
            default=EnvList([]),
        )
        super().register_config()
        self.conf.add_config(
            keys=["commands_pre"],
            of_type=List[Command],
            default=[],
            desc="the commands to be called before testing",
        )
        self.conf.add_config(
            keys=["commands"],
            of_type=List[Command],
            default=[],
            desc="the commands to be called for testing",
        )
        self.conf.add_config(
            keys=["commands_post"],
            of_type=List[Command],
            default=[],
            desc="the commands to be called after testing",
        )
        add_change_dir_conf(self.conf, self.core)
        self.conf.add_config(
            keys=["args_are_paths"],
            of_type=bool,
            default=True,
            desc="if True rewrite relative posargs paths from cwd to change_dir",
        )
        self.conf.add_config(
            keys=["ignore_errors"],
            of_type=bool,
            default=False,
            desc="when executing the commands keep going even if a sub-command exits with non-zero exit code",
        )
        self.conf.add_config(
            keys=["ignore_outcome"],
            of_type=bool,
            default=False,
            desc="if set to true a failing result of this testenv will not make tox fail (instead just warn)",
        )

    def _teardown(self) -> None:
        super()._teardown()
        self._call_pkg_envs("teardown_env", self.conf)

    def interrupt(self) -> None:
        super().interrupt()
        self._call_pkg_envs("interrupt")

    def get_package_env_types(self) -> tuple[str, str] | None:
        if self._register_package_conf():
            has_external_pkg = self.conf["package"] == "external"
            self.core.add_config(
                keys=["package_env", "isolated_build_env"],
                of_type=str,
                default=self._default_package_env,
                desc="tox environment used to package",
            )
            self.conf.add_config(
                keys=["package_env"],
                of_type=str,
                default=f'{self.core["package_env"]}{"_external" if has_external_pkg else ""}',
                desc="tox environment used to package",
            )
            is_external = self.conf["package"] == "external"
            self.conf.add_constant(
                keys=["package_tox_env_type"],
                desc="tox package type used to generate the package",
                value=self._external_pkg_tox_env_type if is_external else self._package_tox_env_type,
            )
            return self.conf["package_env"], self.conf["package_tox_env_type"]
        return None

    def _call_pkg_envs(self, method_name: str, *args: Any) -> None:
        for package_env in self.package_envs:
            with package_env.display_context(suspend=self._has_display_suspended):
                getattr(package_env, method_name)(*args)

    def _clean(self, transitive: bool = False) -> None:  # noqa: FBT001, FBT002
        super()._clean(transitive)
        if transitive:
            self._call_pkg_envs("_clean")

    @property
    def _default_package_env(self) -> str:
        return ".pkg"

    @property
    @abstractmethod
    def _package_tox_env_type(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def _external_pkg_tox_env_type(self) -> str:
        raise NotImplementedError

    def _setup_with_env(self) -> None:
        if self.package_env is not None:
            skip_pkg_install: bool = getattr(self.options, "skip_pkg_install", False)
            if skip_pkg_install is True:
                logging.warning("skip building and installing the package")
            else:
                self._setup_pkg()

    def _register_package_conf(self) -> bool:
        """If this returns True package_env and package_tox_env_type configurations must be defined."""
        self.core.add_config(
            keys=["no_package", "skipsdist"],
            of_type=bool,
            default=False,
            desc="is there any packaging involved in this project",
        )
        core_no_package: bool = self.core["no_package"]
        if core_no_package is True:
            return False
        self.conf.add_config(
            keys="skip_install",
            of_type=bool,
            default=False,
            desc="skip installation",
        )
        skip_install: bool = self.conf["skip_install"]
        return not skip_install

    def _setup_pkg(self) -> None:
        self._packages = self._build_packages()
        if not self.options.package_only:
            self._install(self._packages, RunToxEnv.__name__, "package")
        self._handle_journal_package(self.journal, self._packages)

    @staticmethod
    def _handle_journal_package(journal: EnvJournal, packages: list[Package]) -> None:
        if not journal:
            return
        installed_meta = []
        for package in packages:
            if isinstance(package, PathPackage):
                pkg = package.path
                of_type = "file" if pkg.is_file() else ("dir" if pkg.is_dir() else "N/A")
                meta = {"basename": pkg.name, "type": of_type}
                if of_type == "file":
                    meta["sha256"] = sha256(pkg.read_bytes()).hexdigest()
            else:
                raise NotImplementedError
            installed_meta.append(meta)
        if installed_meta:
            journal["installpkg"] = installed_meta[0] if len(installed_meta) == 1 else installed_meta

    @property
    def environment_variables(self) -> dict[str, str]:
        environment_variables = super().environment_variables
        if self.package_env is not None and self._packages:
            # if package(s) have been built insert them as environment variable
            environment_variables["TOX_PACKAGE"] = os.pathsep.join(str(i) for i in self._packages)
        return environment_variables

    @abstractmethod
    def _build_packages(self) -> list[Package]:
        """:returns: a list of packages installed in the environment"""
        raise NotImplementedError

    @property
    def package_envs(self) -> Iterable[PackageToxEnv]:
        if self.package_env is not None:
            yield self.package_env
            yield from self.package_env.child_pkg_envs(self.conf)

    def mark_active(self) -> None:
        for pkg_env in self.package_envs:
            pkg_env.mark_active_run_env(self)
