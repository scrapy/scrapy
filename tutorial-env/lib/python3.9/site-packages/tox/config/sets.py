from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator, Mapping, Sequence, TypeVar, cast

from .of_type import ConfigConstantDefinition, ConfigDefinition, ConfigDynamicDefinition, ConfigLoadArgs
from .set_env import SetEnv
from .types import EnvList

if TYPE_CHECKING:
    from tox.config.loader.api import Loader
    from tox.config.main import Config

    from .loader.convert import Factory
    from .loader.section import Section

V = TypeVar("V")


class ConfigSet(ABC):
    """A set of configuration that belong together (such as a tox environment settings, core tox settings)."""

    def __init__(self, conf: Config, section: Section, env_name: str | None) -> None:
        self._section = section
        self._env_name = env_name
        self._conf = conf
        self.loaders: list[Loader[Any]] = []  #: active configuration loaders, can alter to change configuration values
        self._defined: dict[str, ConfigDefinition[Any]] = {}
        self._keys: dict[str, None] = {}
        self._alias: dict[str, str] = {}
        self._final = False
        self.register_config()

    @abstractmethod
    def register_config(self) -> None:
        raise NotImplementedError

    def mark_finalized(self) -> None:
        self._final = True

    def add_config(  # noqa: PLR0913
        self,
        keys: str | Sequence[str],
        of_type: type[V],
        default: Callable[[Config, str | None], V] | V,
        desc: str,
        post_process: Callable[[V], V] | None = None,
        factory: Factory[Any] | None = None,
    ) -> ConfigDynamicDefinition[V]:
        """
        Add configuration value.

        :param keys: the keys under what to register the config (first is primary key)
        :param of_type: the type of the config value
        :param default: the default value of the config value
        :param desc: a help message describing the configuration
        :param post_process: a callback to post-process the configuration value after it has been loaded
        :param factory: factory method used to build contained objects (if ``of_type`` is a container type it
          should perform the contained item creation, otherwise creates objects that match the type)
        :return: the new dynamic config definition
        """
        if self._final:
            msg = "config set has been marked final and cannot be extended"
            raise RuntimeError(msg)
        keys_ = self._make_keys(keys)
        definition = ConfigDynamicDefinition(keys_, desc, of_type, default, post_process, factory)
        result = self._add_conf(keys_, definition)
        return cast(ConfigDynamicDefinition[V], result)

    def add_constant(self, keys: str | Sequence[str], desc: str, value: V) -> ConfigConstantDefinition[V]:
        """
        Add a constant value.

        :param keys: the keys under what to register the config (first is primary key)
        :param desc: a help message describing the configuration
        :param value: the config value to use
        :return: the new constant config value
        """
        if self._final:
            msg = "config set has been marked final and cannot be extended"
            raise RuntimeError(msg)
        keys_ = self._make_keys(keys)
        definition = ConfigConstantDefinition(keys_, desc, value)
        result = self._add_conf(keys_, definition)
        return cast(ConfigConstantDefinition[V], result)

    @staticmethod
    def _make_keys(keys: str | Sequence[str]) -> Sequence[str]:
        return (keys,) if isinstance(keys, str) else keys

    def _add_conf(self, keys: Sequence[str], definition: ConfigDefinition[V]) -> ConfigDefinition[V]:
        key = keys[0]
        if key in self._defined:
            self._on_duplicate_conf(key, definition)
        else:
            self._keys[key] = None
            for item in keys:
                self._alias[item] = key
            for key in keys:
                self._defined[key] = definition
        return definition

    def _on_duplicate_conf(self, key: str, definition: ConfigDefinition[V]) -> None:
        earlier = self._defined[key]
        if definition != earlier:  # pragma: no branch
            msg = f"config {key} already defined"
            raise ValueError(msg)

    def __getitem__(self, item: str) -> Any:
        """
        Get the config value for a given key (will materialize in case of dynamic config).

        :param item: the config key
        :return: the configuration value
        """
        return self.load(item)

    def load(self, item: str, chain: list[str] | None = None) -> Any:
        """
        Get the config value for a given key (will materialize in case of dynamic config).

        :param item: the config key
        :param chain: a chain of configuration keys already loaded for this load operation (used to detect circles)
        :return: the configuration value
        """
        config_definition = self._defined[item]
        return config_definition.__call__(self._conf, self.loaders, ConfigLoadArgs(chain, self.name, self.env_name))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(loaders={self.loaders!r})"

    def __iter__(self) -> Iterator[str]:
        """:return: iterate through the defined config keys (primary keys used)"""
        return iter(self._keys.keys())

    def __contains__(self, item: str) -> bool:
        """
        Check if a configuration key is within the config set.

        :param item: the configuration value
        :return: a boolean indicating the truthiness of the statement
        """
        return item in self._alias

    def unused(self) -> list[str]:
        """:return: Return a list of keys present in the config source but not used"""
        found: set[str] = set()
        # keys within loaders (only if the loader is not a parent too)
        parents = {id(i.parent) for i in self.loaders if i.parent is not None}
        for loader in self.loaders:
            if id(loader) not in parents:
                found.update(loader.found_keys())
        found -= self._defined.keys()
        return sorted(found)

    def primary_key(self, key: str) -> str:
        """
        Get the primary key for a config key.

        :param key: the config key
        :return: the key that's considered the primary for the input key
        """
        return self._alias[key]

    @property
    def name(self) -> str:
        return self._section.name

    @property
    def env_name(self) -> str | None:
        return self._env_name


class CoreConfigSet(ConfigSet):
    """Configuration set for the core tox config."""

    def __init__(self, conf: Config, section: Section, root: Path, src_path: Path) -> None:
        self._root = root
        self._src_path = src_path
        super().__init__(conf, section=section, env_name=None)
        desc = "define environments to automatically run"
        self.add_config(keys=["env_list", "envlist"], of_type=EnvList, default=EnvList([]), desc=desc)

    def _default_work_dir(self, conf: Config, env_name: str | None) -> Path:  # noqa: ARG002
        return cast(Path, self["tox_root"] / ".tox")

    def _default_temp_dir(self, conf: Config, env_name: str | None) -> Path:  # noqa: ARG002
        return cast(Path, self["work_dir"] / ".tmp")

    def _work_dir_post_process(self, folder: Path) -> Path:
        return self._conf.work_dir if self._conf.options.work_dir else folder

    def register_config(self) -> None:
        self.add_constant(keys=["config_file_path"], desc="path to the configuration file", value=self._src_path)
        self.add_config(
            keys=["tox_root", "toxinidir"],
            of_type=Path,
            default=self._root,
            desc="the root directory (where the configuration file is found)",
        )

        self.add_config(
            keys=["work_dir", "toxworkdir"],
            of_type=Path,
            default=self._default_work_dir,
            post_process=self._work_dir_post_process,
            desc="working directory",
        )
        self.add_config(
            keys=["temp_dir"],
            of_type=Path,
            default=self._default_temp_dir,
            desc="a folder for temporary files (is not cleaned at start)",
        )
        self.add_constant("host_python", "the host python executable path", sys.executable)

    def _on_duplicate_conf(self, key: str, definition: ConfigDefinition[V]) -> None:
        pass  # core definitions may be defined multiple times as long as all their options match, first defined wins


class EnvConfigSet(ConfigSet):
    """Configuration set for a tox environment."""

    def __init__(self, conf: Config, section: Section, env_name: str) -> None:
        super().__init__(conf, section, env_name)
        self.default_set_env_loader: Callable[[], Mapping[str, str]] = lambda: {}

    def register_config(self) -> None:
        def set_env_post_process(values: SetEnv) -> SetEnv:
            values.update(self.default_set_env_loader(), override=False)
            values.update({"PYTHONIOENCODING": "utf-8"}, override=True)
            return values

        def set_env_factory(raw: object) -> SetEnv:
            if not isinstance(raw, str):
                raise TypeError(raw)
            return SetEnv(raw, self.name, self.env_name, root)

        root = self._conf.core["tox_root"]
        self.add_config(
            keys=["set_env", "setenv"],
            of_type=SetEnv,
            factory=set_env_factory,
            default=SetEnv("", self.name, self.env_name, root),
            desc="environment variables to set when running commands in the tox environment",
            post_process=set_env_post_process,
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self._env_name!r}, loaders={self.loaders!r})"


__all__ = (
    "ConfigSet",
    "CoreConfigSet",
    "EnvConfigSet",
)
