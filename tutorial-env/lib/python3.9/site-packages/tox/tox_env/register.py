"""Manages the tox environment registry."""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from tox.plugin.manager import Plugin

    from .package import PackageToxEnv
    from .runner import RunToxEnv


class ToxEnvRegister:
    """tox environment registry."""

    def __init__(self) -> None:
        self._run_envs: dict[str, type[RunToxEnv]] = {}
        self._package_envs: dict[str, type[PackageToxEnv]] = {}
        self._default_run_env: str = ""

    def _register_tox_env_types(self, manager: Plugin) -> None:
        manager.tox_register_tox_env(register=self)

    def add_run_env(self, of_type: type[RunToxEnv]) -> None:
        """
        Define a new run tox environment type.

        :param of_type: the new run environment type
        """
        self._run_envs[of_type.id()] = of_type

    def add_package_env(self, of_type: type[PackageToxEnv]) -> None:
        """
        Define a new packaging tox environment type.

        :param of_type: the new packaging environment type
        """
        self._package_envs[of_type.id()] = of_type

    @property
    def env_runners(self) -> Iterable[str]:
        """:returns: run environment types currently defined"""
        return self._run_envs.keys()

    @property
    def default_env_runner(self) -> str:
        """:returns: the default run environment type"""
        if not self._default_run_env and self._run_envs:
            self._default_run_env = next(iter(self._run_envs.keys()))
        return self._default_run_env

    @default_env_runner.setter
    def default_env_runner(self, value: str) -> None:
        """
        Change the default run environment type.

        :param value: the new run environment type by name
        """
        if value not in self._run_envs:
            msg = "run env must be registered before setting it as default"
            raise ValueError(msg)
        self._default_run_env = value

    def runner(self, name: str) -> type[RunToxEnv]:
        """
        Lookup a run tox environment type by name.

        :param name: the name of the runner type
        :return: the type of the runner type
        """
        return self._run_envs[name]

    def package(self, name: str) -> type[PackageToxEnv]:
        """
        Lookup a packaging tox environment type by name.

        :param name: the name of the packaging type
        :return: the type of the packaging type
        """
        return self._package_envs[name]


REGISTER = ToxEnvRegister()  #: the tox register

__all__ = (
    "REGISTER",
    "ToxEnvRegister",
)
