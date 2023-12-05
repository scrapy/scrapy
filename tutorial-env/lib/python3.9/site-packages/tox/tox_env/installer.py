from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from tox.tox_env.api import ToxEnv

T = TypeVar("T", bound="ToxEnv")


class Installer(ABC, Generic[T]):
    def __init__(self, tox_env: T) -> None:
        self._env = tox_env
        self._register_config()

    @abstractmethod
    def _register_config(self) -> None:
        """Register configurations for the installer."""
        raise NotImplementedError

    @abstractmethod
    def installed(self) -> Any:
        """:returns: a list of packages installed (JSON dump-able)"""
        raise NotImplementedError

    @abstractmethod
    def install(self, arguments: Any, section: str, of_type: str) -> None:
        raise NotImplementedError
