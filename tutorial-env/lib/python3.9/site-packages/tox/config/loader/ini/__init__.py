from __future__ import annotations

import inspect
import re
from typing import TYPE_CHECKING, TypeVar

from tox.config.loader.api import ConfigLoadArgs, Loader, Override
from tox.config.loader.ini.factor import filter_for_env
from tox.config.loader.ini.replace import replace
from tox.config.loader.str_convert import StrConvert
from tox.config.set_env import SetEnv
from tox.report import HandledError

if TYPE_CHECKING:
    from configparser import ConfigParser, SectionProxy

    from tox.config.loader.convert import Factory
    from tox.config.loader.section import Section
    from tox.config.main import Config

V = TypeVar("V")
_COMMENTS = re.compile(r"(\s)*(?<!\\)#.*")


class IniLoader(StrConvert, Loader[str]):
    """Load configuration from an ini section (ini file is a string to string dictionary)."""

    def __init__(  # noqa: PLR0913
        self,
        section: Section,
        parser: ConfigParser,
        overrides: list[Override],
        core_section: Section,
        section_key: str | None = None,
    ) -> None:
        self._section_proxy: SectionProxy = parser[section_key or section.key]
        self._parser = parser
        self.core_section = core_section
        super().__init__(section, overrides)

    def load_raw(self, key: str, conf: Config | None, env_name: str | None) -> str:
        return self.process_raw(conf, env_name, self._section_proxy[key])

    @staticmethod
    def process_raw(conf: Config | None, env_name: str | None, value: str) -> str:
        # strip comments
        elements: list[str] = []
        for line in value.split("\n"):
            if not line.startswith("#"):
                part = _COMMENTS.sub("", line)
                elements.append(part.replace("\\#", "#"))
        strip_comments = "\n".join(elements)
        if conf is None:  # noqa: SIM108 # conf is None when we're loading the global tox configuration file for the CLI
            factor_filtered = strip_comments  # we don't support factor and replace functionality there
        else:
            factor_filtered = filter_for_env(strip_comments, env_name)  # select matching factors
        return factor_filtered.replace("\r", "").replace("\\\n", "")  # collapse explicit new-line escape

    def build(  # noqa: PLR0913
        self,
        key: str,
        of_type: type[V],
        factory: Factory[V],
        conf: Config | None,
        raw: str,
        args: ConfigLoadArgs,
    ) -> V:
        delay_replace = inspect.isclass(of_type) and issubclass(of_type, SetEnv)

        def replacer(raw_: str, args_: ConfigLoadArgs) -> str:
            if conf is None:
                replaced = raw_  # no replacement supported in the core section
            else:
                try:
                    replaced = replace(conf, self, raw_, args_)  # do replacements
                except Exception as exception:  # noqa: BLE001
                    if isinstance(exception, HandledError):
                        raise
                    name = self.core_section.key if args_.env_name is None else args_.env_name
                    msg = f"replace failed in {name}.{key} with {exception!r}"
                    raise HandledError(msg) from exception
            return replaced

        prepared = replacer(raw, args) if not delay_replace else raw
        converted = self.to(prepared, of_type, factory)
        if delay_replace:
            converted.use_replacer(replacer, args)  # type: ignore[attr-defined] # this can be only set_env that has it
        return converted

    def found_keys(self) -> set[str]:
        return set(self._section_proxy.keys())

    def get_section(self, name: str) -> SectionProxy | None:
        # needed for non tox environment replacements
        if self._parser.has_section(name):
            return self._parser[name]
        return None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(section={self._section.key}, overrides={self.overrides!r})"
