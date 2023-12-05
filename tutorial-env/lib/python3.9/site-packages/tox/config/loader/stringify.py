from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence, Set

from tox.config.set_env import SetEnv
from tox.config.types import Command, EnvList
from tox.tox_env.python.pip.req_file import PythonDeps


def stringify(value: Any) -> tuple[str, bool]:  # noqa: PLR0911
    """
    Transform a value into a string representation.

    :param value: the value in question
    :return: a tuple, first the value as str, second a flag if the value if a multi-line one
    """
    if isinstance(value, str):
        return value, False
    if isinstance(value, (Path, float, int, bool)):
        return str(value), False
    if isinstance(value, Mapping):
        return "\n".join(f"{stringify(k)[0]}={stringify(v)[0]}" for k, v in value.items()), True
    if isinstance(value, (Sequence, Set)):
        return "\n".join(stringify(i)[0] for i in value), True
    if isinstance(value, EnvList):
        return "\n".join(e for e in value.envs), True
    if isinstance(value, Command):
        return value.shell, True
    if isinstance(value, SetEnv):
        env_var_keys = sorted(value)
        return stringify({k: value.load(k) for k in env_var_keys})
    if isinstance(value, PythonDeps):
        return stringify(value.lines())
    return str(value), False


__all__ = ("stringify",)
