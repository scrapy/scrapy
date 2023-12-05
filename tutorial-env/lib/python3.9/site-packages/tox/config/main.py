from __future__ import annotations

import os
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Sequence, TypeVar

from .sets import ConfigSet, CoreConfigSet, EnvConfigSet

if TYPE_CHECKING:
    from tox.config.loader.api import Loader, OverrideMap

    from .cli.parser import Parsed
    from .loader.memory import MemoryLoader
    from .loader.section import Section
    from .source import Source


T = TypeVar("T", bound=ConfigSet)


class Config:
    """Main configuration object for tox."""

    def __init__(  # noqa: PLR0913
        self,
        config_source: Source,
        options: Parsed,
        root: Path,
        pos_args: Sequence[str] | None,
        work_dir: Path,
    ) -> None:
        self._pos_args = None if pos_args is None else tuple(pos_args)
        self._work_dir = work_dir
        self._root = root
        self._options = options

        self._overrides: OverrideMap = defaultdict(list)
        for override in options.override:
            self._overrides[override.namespace].append(override)

        self._src = config_source
        self._key_to_conf_set: dict[tuple[str, str], ConfigSet] = OrderedDict()
        self._core_set: CoreConfigSet | None = None
        self.memory_seed_loaders: defaultdict[str, list[MemoryLoader]] = defaultdict(list)

    def pos_args(self, to_path: Path | None) -> tuple[str, ...] | None:
        """
        :param to_path: if not None rewrite relative posargs paths from cwd to to_path
        :return: positional argument
        """
        if self._pos_args is not None and to_path is not None and Path.cwd() != to_path:
            args = []
            # we use os.path to unroll .. in path without resolve
            to_path_str = os.path.abspath(str(to_path))  # noqa: PTH100
            for arg in self._pos_args:
                path_arg = Path(arg)
                if path_arg.exists() and not path_arg.is_absolute():
                    # we use os.path to unroll .. in path without resolve
                    path_arg_str = os.path.abspath(str(path_arg))  # noqa: PTH100
                    # we use os.path to not fail when not within
                    relative = os.path.relpath(path_arg_str, to_path_str)
                    args.append(relative)
                else:
                    args.append(arg)
            return tuple(args)
        return self._pos_args

    @property
    def work_dir(self) -> Path:
        """:return: working directory for this project"""
        return self._work_dir

    @property
    def src_path(self) -> Path:
        """:return: the location of the tox configuration source"""
        return self._src.path

    def __iter__(self) -> Iterator[str]:
        """:return: an iterator that goes through existing environments"""
        return self._src.envs(self.core)

    def sections(self) -> Iterator[Section]:
        yield from self._src.sections()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(config_source={self._src!r})"

    def __contains__(self, item: str) -> bool:
        """:return: check if an environment already exists"""
        return any(name for name in self if name == item)

    @classmethod
    def make(cls, parsed: Parsed, pos_args: Sequence[str] | None, source: Source) -> Config:
        """Make a tox configuration object."""
        # root is the project root, where the configuration file is at
        # work dir is where we put our own files
        root: Path = source.path.parent if parsed.root_dir is None else parsed.root_dir
        work_dir: Path = source.path.parent if parsed.work_dir is None else parsed.work_dir
        # if these are relative we need to expand them them to ensure paths built on this can resolve independent on cwd
        root = root.resolve()
        work_dir = work_dir.resolve()
        return cls(
            config_source=source,
            options=parsed,
            pos_args=pos_args,
            root=root,
            work_dir=work_dir,
        )

    @property
    def options(self) -> Parsed:
        return self._options

    @property
    def core(self) -> CoreConfigSet:
        """:return: the core configuration"""
        if self._core_set is not None:
            return self._core_set
        core_section = self._src.get_core_section()
        core = CoreConfigSet(self, core_section, self._root, self.src_path)
        core.loaders.extend(self._src.get_loaders(core_section, base=[], override_map=self._overrides, conf=core))
        self._core_set = core
        return core

    def get_section_config(  # noqa: PLR0913
        self,
        section: Section,
        base: list[str] | None,
        of_type: type[T],
        for_env: str | None,
        loaders: Sequence[Loader[Any]] | None = None,
    ) -> T:
        key = section.key, for_env or ""
        try:
            return self._key_to_conf_set[key]  # type: ignore[return-value] # expected T but found ConfigSet
        except KeyError:
            conf_set = of_type(self, section, for_env)
            self._key_to_conf_set[key] = conf_set
            if for_env is not None:
                conf_set.loaders.extend(self.memory_seed_loaders.get(for_env, []))
            for loader in self._src.get_loaders(section, base, self._overrides, conf_set):
                conf_set.loaders.append(loader)
            if loaders is not None:
                conf_set.loaders.extend(loaders)
            return conf_set

    def get_env(
        self,
        item: str,
        package: bool = False,  # noqa: FBT001, FBT002
        loaders: Sequence[Loader[Any]] | None = None,
    ) -> EnvConfigSet:
        """
        Return the configuration for a given tox environment (will create if not exist yet).

        :param item: the name of the environment
        :param package: a flag indicating if the environment is of type packaging or not (only used for creation)
        :param loaders: loaders to use for this configuration (only used for creation)
        :return: the tox environments config
        """
        section, base_test, base_pkg = self._src.get_tox_env_section(item)
        return self.get_section_config(
            section,
            base=base_pkg if package else base_test,
            of_type=EnvConfigSet,
            for_env=item,
            loaders=loaders,
        )

    def clear_env(self, name: str) -> None:
        section, _, __ = self._src.get_tox_env_section(name)
        del self._key_to_conf_set[(section.key, name)]


___all__ = [
    "Config",
]
