"""Provides configuration values from the environment variables."""
from __future__ import annotations

import logging
import os
from typing import Any, List

from tox.config.loader.str_convert import StrConvert

CONVERT = StrConvert()


def get_env_var(key: str, of_type: type[Any]) -> tuple[Any, str] | None:
    """
    Get the environment variable option.

    :param key: the config key requested
    :param of_type: the type we would like to convert it to
    :return:
    """
    key_upper = key.upper()
    for environ_key in (f"TOX_{key_upper}", f"TOX{key_upper}"):
        if environ_key in os.environ:
            value = os.environ[environ_key]
            origin = getattr(of_type, "__origin__", of_type.__class__)
            try:
                if origin in (list, List):
                    entry_type = of_type.__args__[0]
                    result = [CONVERT.to(raw=v, of_type=entry_type, factory=None) for v in value.split(";")]
                else:
                    result = CONVERT.to(raw=value, of_type=of_type, factory=None)
            except Exception as exception:  # noqa: BLE001
                logging.warning(
                    "env var %s=%r cannot be transformed to %r because %r",
                    environ_key,
                    value,
                    of_type,
                    exception,
                )
            else:
                return result, f"env var {environ_key}"
    return None


__all__ = ("get_env_var",)
