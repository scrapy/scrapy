"""Declare the abstract base class for tox environments that handle the Python language via the virtualenv project."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from virtualenv import __version__ as virtualenv_version
from virtualenv import session_via_cli

from tox.config.loader.str_convert import StrConvert
from tox.execute.local_sub_process import LocalSubProcessExecutor
from tox.tox_env.python.api import Python, PythonInfo
from tox.tox_env.python.pip.pip_install import Pip

if TYPE_CHECKING:
    from virtualenv.create.creator import Creator
    from virtualenv.run.session import Session

    from tox.execute.api import Execute
    from tox.tox_env.api import ToxEnvCreateArgs


class VirtualEnv(Python):
    """A python executor that uses the virtualenv project with pip."""

    def __init__(self, create_args: ToxEnvCreateArgs) -> None:
        self._virtualenv_session: Session | None = None
        self._executor: Execute | None = None
        self._installer: Pip | None = None
        super().__init__(create_args)

    def register_config(self) -> None:
        super().register_config()
        self.conf.add_config(
            keys=["system_site_packages", "sitepackages"],
            of_type=bool,
            default=lambda conf, name: StrConvert().to_bool(  # noqa: ARG005
                self.environment_variables.get("VIRTUALENV_SYSTEM_SITE_PACKAGES", "False"),
            ),
            desc="create virtual environments that also have access to globally installed packages.",
        )
        self.conf.add_config(
            keys=["always_copy", "alwayscopy"],
            of_type=bool,
            default=lambda conf, name: StrConvert().to_bool(  # noqa: ARG005
                self.environment_variables.get(
                    "VIRTUALENV_COPIES",
                    self.environment_variables.get("VIRTUALENV_ALWAYS_COPY", "False"),
                ),
            ),
            desc="force virtualenv to always copy rather than symlink",
        )
        self.conf.add_config(
            keys=["download"],
            of_type=bool,
            default=lambda conf, name: StrConvert().to_bool(  # noqa: ARG005
                self.environment_variables.get("VIRTUALENV_DOWNLOAD", "False"),
            ),
            desc="true if you want virtualenv to upgrade pip/wheel/setuptools to the latest version",
        )

    @property
    def executor(self) -> Execute:
        if self._executor is None:
            self._executor = LocalSubProcessExecutor(self.options.is_colored)
        return self._executor

    @property
    def installer(self) -> Pip:
        if self._installer is None:
            self._installer = Pip(self)
        return self._installer

    def python_cache(self) -> dict[str, Any]:
        base = super().python_cache()
        base.update(
            {
                "executable": str(self.base_python.extra["executable"]),
                "virtualenv version": virtualenv_version,
            },
        )
        return base

    def _get_env_journal_python(self) -> dict[str, Any]:
        base = super()._get_env_journal_python()
        base["executable"] = str(self.base_python.extra["executable"])
        return base

    def _default_pass_env(self) -> list[str]:
        env = super()._default_pass_env()
        env.append("PIP_*")  # we use pip as installer
        env.append("VIRTUALENV_*")  # we use virtualenv as isolation creator
        return env

    def _default_set_env(self) -> dict[str, str]:
        env = super()._default_set_env()
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        return env

    @property
    def session(self) -> Session:
        if self._virtualenv_session is None:
            env_dir = [str(self.env_dir)]
            env = self.virtualenv_env_vars()
            self._virtualenv_session = session_via_cli(env_dir, options=None, setup_logging=False, env=env)
        return self._virtualenv_session

    def virtualenv_env_vars(self) -> dict[str, str]:
        env = self.environment_variables.copy()
        base_python: list[str] = self.conf["base_python"]
        if "VIRTUALENV_NO_PERIODIC_UPDATE" not in env:
            env["VIRTUALENV_NO_PERIODIC_UPDATE"] = "True"
        env["VIRTUALENV_CLEAR"] = "False"
        env["VIRTUALENV_SYSTEM_SITE_PACKAGES"] = str(self.conf["system_site_packages"])
        env["VIRTUALENV_COPIES"] = str(self.conf["always_copy"])
        env["VIRTUALENV_DOWNLOAD"] = str(self.conf["download"])
        env["VIRTUALENV_PYTHON"] = "\n".join(base_python)
        if hasattr(self.options, "discover"):
            env["VIRTUALENV_TRY_FIRST_WITH"] = os.pathsep.join(self.options.discover)
        return env

    @property
    def creator(self) -> Creator:
        return self.session.creator

    def create_python_env(self) -> None:
        self.session.run()

    def _get_python(self, base_python: list[str]) -> PythonInfo | None:  # noqa: ARG002
        # the base pythons are injected into the virtualenv_env_vars, so we don't need to use it here
        try:
            interpreter = self.creator.interpreter
        except (FileNotFoundError, RuntimeError):  # Unable to find the interpreter
            return None
        return PythonInfo(
            implementation=interpreter.implementation,
            version_info=interpreter.version_info,
            version=interpreter.version,
            is_64=(interpreter.architecture == 64),  # noqa: PLR2004
            platform=interpreter.platform,
            extra={"executable": Path(interpreter.system_executable).resolve()},
        )

    def prepend_env_var_path(self) -> list[Path]:
        """Paths to add to the executable."""
        # we use the original executable as shims may be somewhere else
        return list(dict.fromkeys((self.creator.bin_dir, self.creator.script_dir)))

    def env_site_package_dir(self) -> Path:
        return cast(Path, self.creator.purelib)

    def env_python(self) -> Path:
        return cast(Path, self.creator.exe)

    def env_bin_dir(self) -> Path:
        return cast(Path, self.creator.script_dir)

    @property
    def runs_on_platform(self) -> str:
        return sys.platform

    @property
    def environment_variables(self) -> dict[str, str]:
        environment_variables = super().environment_variables
        environment_variables["VIRTUAL_ENV"] = str(self.conf["env_dir"])
        return environment_variables
