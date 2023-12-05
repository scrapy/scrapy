"""Sources."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Iterator, List

from tox.config.loader.section import Section

if TYPE_CHECKING:
    from pathlib import Path

    from tox.config.loader.api import Loader, OverrideMap
    from tox.config.sets import ConfigSet, CoreConfigSet


class Source(ABC):
    """Source is able to return a configuration value (for either the core or per environment source)."""

    FILENAME = ""

    def __init__(self, path: Path) -> None:
        self.path: Path = path  #: the path to the configuration source
        self._section_to_loaders: dict[str, list[Loader[Any]]] = {}

    def get_loaders(
        self,
        section: Section,
        base: list[str] | None,
        override_map: OverrideMap,
        conf: ConfigSet,
    ) -> Iterator[Loader[Any]]:
        """
        Return a loader that loads settings from a given section name.

        :param section: the section to load
        :param base: base sections to fallback to
        :param override_map: a list of overrides to apply
        :param conf: the config set to use
        :returns: the loaders to use
        """
        section = self.transform_section(section)
        key = section.key
        if key in self._section_to_loaders:
            yield from self._section_to_loaders[key]
            return
        loaders: list[Loader[Any]] = []
        self._section_to_loaders[key] = loaders
        loader: Loader[Any] | None = self.get_loader(section, override_map)
        if loader is not None:
            loaders.append(loader)
            yield loader

        if base is not None:
            conf.add_config(
                keys="base",
                of_type=List[str],
                desc="inherit missing keys from these sections",
                default=base,
            )
            for base_section in self.get_base_sections(conf["base"], section):
                child = loader
                loader = self.get_loader(base_section, override_map)
                if loader is None:
                    loader = child
                    continue
                if child is not None and loader is not None:
                    child.parent = loader
                yield loader
                loaders.append(loader)

    @abstractmethod
    def transform_section(self, section: Section) -> Section:
        raise NotImplementedError

    @abstractmethod
    def get_loader(self, section: Section, override_map: OverrideMap) -> Loader[Any] | None:
        raise NotImplementedError

    @abstractmethod
    def get_base_sections(self, base: list[str], in_section: Section) -> Iterator[Section]:
        raise NotImplementedError

    @abstractmethod
    def sections(self) -> Iterator[Section]:
        """
        Return a loader that loads the core configuration values.

        :returns: the core loader from this source
        """
        raise NotImplementedError

    @abstractmethod
    def envs(self, core_conf: CoreConfigSet) -> Iterator[str]:
        """
        :param core_conf: the core configuration set
        :returns: a list of environments defined within this source
        """
        raise NotImplementedError

    @abstractmethod
    def get_tox_env_section(self, item: str) -> tuple[Section, list[str], list[str]]:
        """:returns: the section for a tox environment"""
        raise NotImplementedError

    @abstractmethod
    def get_core_section(self) -> Section:
        """:returns: the core section"""
        raise NotImplementedError


__all__ = [
    "Section",
    "Source",
]
