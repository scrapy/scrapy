"""Provides configuration values from tox.ini files."""
from __future__ import annotations

import logging
import os
from configparser import ConfigParser
from pathlib import Path
from typing import Any, ClassVar

from platformdirs import user_config_dir

from tox.config.loader.api import ConfigLoadArgs
from tox.config.loader.ini import IniLoader
from tox.config.source.ini_section import CORE

DEFAULT_CONFIG_FILE = Path(user_config_dir("tox")) / "config.ini"


class IniConfig:
    TOX_CONFIG_FILE_ENV_VAR = "TOX_USER_CONFIG_FILE"
    STATE: ClassVar[dict[bool | None, str]] = {None: "failed to parse", True: "active", False: "missing"}

    def __init__(self) -> None:
        config_file = os.environ.get(self.TOX_CONFIG_FILE_ENV_VAR, None)
        self.is_env_var = config_file is not None
        self.config_file = Path(config_file if config_file is not None else DEFAULT_CONFIG_FILE)
        self._cache: dict[tuple[str, type[Any]], Any] = {}
        self.has_config_file: bool | None = self.config_file.exists()
        self.ini: IniLoader | None = None

        if self.has_config_file:
            self.config_file = self.config_file.absolute()
            try:
                parser = ConfigParser(interpolation=None)
                with self.config_file.open() as file_handler:
                    parser.read_file(file_handler)
                self.has_tox_section = parser.has_section(CORE.key)
                if self.has_tox_section:
                    self.ini = IniLoader(CORE, parser, overrides=[], core_section=CORE)
            except Exception as exception:  # noqa: BLE001
                logging.error("failed to read config file %s because %r", config_file, exception)  # noqa: TRY400
                self.has_config_file = None

    def get(self, key: str, of_type: type[Any]) -> Any:
        cache_key = key, of_type
        if cache_key in self._cache:
            result = self._cache[cache_key]
        else:
            try:
                if self.ini is None:  # pragma: no cover # this can only happen if we don't call __bool__ firsts
                    result = None
                else:
                    source = "file"
                    args = ConfigLoadArgs(chain=[key], name=CORE.prefix, env_name=None)
                    value = self.ini.load(key, of_type=of_type, conf=None, factory=None, args=args)
                    result = value, source
            except KeyError:  # just not found
                result = None
            except Exception as exception:  # noqa: BLE001
                logging.warning("%s key %s as type %r failed with %r", self.config_file, key, of_type, exception)
                result = None
        self._cache[cache_key] = result
        return result

    def __bool__(self) -> bool:
        return bool(self.has_config_file) and bool(self.has_tox_section)

    @property
    def epilog(self) -> str:
        # text to show within the parsers epilog
        return (
            f"{os.linesep}config file {str(self.config_file)!r} {self.STATE[self.has_config_file]} "
            f"(change{'d' if self.is_env_var else ''} via env var {self.TOX_CONFIG_FILE_ENV_VAR})"
        )
