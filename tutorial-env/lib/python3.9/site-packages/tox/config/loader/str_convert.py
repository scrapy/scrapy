"""Convert string configuration values to tox python configuration objects."""
from __future__ import annotations

import shlex
import sys
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from tox.config.loader.convert import Convert
from tox.config.types import Command, EnvList

if TYPE_CHECKING:
    from typing import Final


class StrConvert(Convert[str]):
    """A class converting string values to tox types."""

    @staticmethod
    def to_str(value: str) -> str:
        return str(value).strip()

    @staticmethod
    def to_path(value: str) -> Path:
        return Path(value)

    @staticmethod
    def to_list(value: str, of_type: type[Any]) -> Iterator[str]:
        splitter = "\n" if issubclass(of_type, Command) or "\n" in value else ","
        splitter = splitter.replace("\r", "")
        for token in value.split(splitter):
            value = token.strip()
            if value:
                yield value

    @staticmethod
    def to_set(value: str, of_type: type[Any]) -> Iterator[str]:
        yield from StrConvert.to_list(value, of_type)

    @staticmethod
    def to_dict(value: str, of_type: tuple[type[Any], type[Any]]) -> Iterator[tuple[str, str]]:  # noqa: ARG004
        for row in value.split("\n"):
            if row.strip():
                key, sep, value = row.partition("=")
                if sep:
                    yield key.strip(), value.strip()
                else:
                    msg = f"dictionary lines must be of form key=value, found {row!r}"
                    raise TypeError(msg)

    @staticmethod
    def _win32_process_path_backslash(value: str, escape: str, special_chars: str) -> str:
        """
        Escape backslash in value that is not followed by a special character.

        This allows windows paths to be written without double backslash, while
        retaining the POSIX backslash escape semantics for quotes and escapes.
        """
        result = []
        for ix, char in enumerate(value):
            result.append(char)
            if char == escape:
                last_char = value[ix - 1 : ix]
                if last_char == escape:
                    continue
                next_char = value[ix + 1 : ix + 2]
                if next_char not in (escape, *special_chars):
                    result.append(escape)  # escape escapes that are not themselves escaping a special character
        return "".join(result)

    @staticmethod
    def to_command(value: str) -> Command:
        """
        At this point, ``value`` has already been substituted out, and all punctuation / escapes are final.

        Value will typically be stripped of whitespace when coming from an ini file.
        """
        value = value.replace(r"\#", "#")
        is_win = sys.platform == "win32"
        if is_win:  # pragma: win32 cover
            s = shlex.shlex(posix=True)
            value = StrConvert._win32_process_path_backslash(
                value,
                escape=s.escape,
                special_chars=s.quotes + s.whitespace,
            )
        splitter = shlex.shlex(value, posix=True)
        splitter.whitespace_split = True
        splitter.commenters = ""  # comments handled earlier, and the shlex does not know escaped comment characters
        args: list[str] = []
        pos = 0
        try:
            for arg in splitter:
                if is_win and len(arg) > 1 and arg[0] == arg[-1] and arg.startswith(("'", '"')):  # pragma: win32 cover
                    # on Windows quoted arguments will remain quoted, strip it
                    arg = arg[1:-1]  # noqa: PLW2901
                args.append(arg)
                pos = splitter.instream.tell()
        except ValueError:
            args.append(value[pos:])
        if len(args) == 0:
            msg = f"attempting to parse {value!r} into a command failed"
            raise ValueError(msg)
        if args[0] != "-" and args[0].startswith("-"):
            args[0] = args[0][1:]
            args = ["-", *args]
        return Command(args)

    @staticmethod
    def to_env_list(value: str) -> EnvList:
        from tox.config.loader.ini.factor import extend_factors

        elements = list(chain.from_iterable(extend_factors(expr) for expr in value.split("\n")))
        return EnvList(elements)

    TRUTHFUL_VALUES: Final[set[str]] = {"true", "1", "yes", "on"}
    FALSE_VALUES: Final[set[str]] = {"false", "0", "no", "off", ""}
    VALID_BOOL = sorted(TRUTHFUL_VALUES | FALSE_VALUES)

    @staticmethod
    def to_bool(value: str) -> bool:
        norm = str(value).strip().lower()
        if norm in StrConvert.TRUTHFUL_VALUES:
            return True
        if norm in StrConvert.FALSE_VALUES:
            return False

        msg = f"value {value!r} cannot be transformed to bool, valid: {', '.join(StrConvert.VALID_BOOL)}"
        raise TypeError(msg)


__all__ = ("StrConvert",)
