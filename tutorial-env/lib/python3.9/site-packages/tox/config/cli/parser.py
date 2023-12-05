"""Customize argparse logic for tox (also contains the base options)."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from argparse import SUPPRESS, Action, ArgumentDefaultsHelpFormatter, ArgumentParser, Namespace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, Optional, Sequence, Tuple, Type, TypeVar, cast

from tox.config.loader.str_convert import StrConvert
from tox.plugin import NAME

from .env_var import get_env_var
from .ini import IniConfig

if TYPE_CHECKING:
    from tox.session.state import State


class ArgumentParserWithEnvAndConfig(ArgumentParser):
    """Argument parser which updates its defaults by checking the configuration files and environmental variables."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # sub-parsers also construct an instance of the parser, but they don't get their own file config, but inherit
        self.file_config = kwargs.pop("file_config") if "file_config" in kwargs else IniConfig()
        kwargs["epilog"] = self.file_config.epilog
        super().__init__(*args, **kwargs)

    def fix_defaults(self) -> None:
        for action in self._actions:
            self.fix_default(action)

    def fix_default(self, action: Action) -> None:
        if hasattr(action, "default") and hasattr(action, "dest") and action.default != SUPPRESS:
            of_type = self.get_type(action)
            key = action.dest
            outcome = get_env_var(key, of_type=of_type)
            if outcome is None and self.file_config:
                outcome = self.file_config.get(key, of_type=of_type)
            if outcome is not None:
                action.default, default_value = outcome
                action.default_source = default_value  # type: ignore[attr-defined]
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            for values in action.choices.values():
                if not isinstance(values, ToxParser):  # pragma: no cover
                    msg = "detected sub-parser added without using our own add command"
                    raise RuntimeError(msg)  # noqa: TRY004
                values.fix_defaults()

    @staticmethod
    def get_type(action: Action) -> type[Any]:
        of_type: type[Any] | None = getattr(action, "of_type", None)
        if of_type is None:
            if isinstance(action, argparse._AppendAction):  # noqa: SLF001
                of_type = List[action.type]  # type: ignore[name-defined]
            elif isinstance(action, argparse._StoreAction) and action.choices:  # noqa: SLF001
                loc = locals()
                loc["Literal"] = Literal
                as_literal = f"Literal[{', '.join(repr(i) for i in action.choices)}]"
                of_type = eval(as_literal, globals(), loc)  # noqa: PGH001, S307
            elif action.default is not None:
                of_type = type(action.default)
            elif isinstance(action, argparse._StoreConstAction) and action.const is not None:  # noqa: SLF001
                of_type = type(action.const)
            else:
                raise TypeError(action)
        return of_type

    def parse_args(  # type: ignore[override] # avoid defining all overloads
        self,
        args: Sequence[str] | None = None,
        namespace: Namespace | None = None,
    ) -> Namespace:
        res, argv = self.parse_known_args(args, namespace)
        if argv:
            self.error(
                f'unrecognized arguments: {" ".join(argv)}\n'
                "hint: if you tried to pass arguments to a command use -- to separate them from tox ones",
            )
        return res


class HelpFormatter(ArgumentDefaultsHelpFormatter):
    """A help formatter that provides the default value and the source it comes from."""

    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=30, width=240)

    def _get_help_string(self, action: Action) -> str | None:
        text: str = super()._get_help_string(action) or ""
        if hasattr(action, "default_source"):
            default = " (default: %(default)s)"
            if text.endswith(default):  # pragma: no branch
                text = f"{text[: -len(default)]} (default: %(default)s -> from %(default_source)s)"
        return text

    def add_raw_text(self, text: str | None) -> None:
        def keep(content: str) -> str:
            return content

        if text is not SUPPRESS and text is not None:
            self._add_item(keep, [text])


ToxParserT = TypeVar("ToxParserT", bound="ToxParser")
DEFAULT_VERBOSITY = 2


class Parsed(Namespace):
    """CLI options."""

    @property
    def verbosity(self) -> int:
        """:return: reporting verbosity"""
        result: int = max(self.verbose - self.quiet, 0)
        return result

    @property
    def is_colored(self) -> bool:
        """:return: flag indicating if the output is colored or not"""
        return cast(bool, self.colored == "yes")

    exit_and_dump_after: int


ArgumentArgs = Tuple[Tuple[str, ...], Optional[Type[Any]], Dict[str, Any]]


class ToxParser(ArgumentParserWithEnvAndConfig):
    """Argument parser for tox."""

    def __init__(self, *args: Any, root: bool = False, add_cmd: bool = False, **kwargs: Any) -> None:
        self.of_cmd: str | None = None
        self.handlers: dict[str, tuple[Any, Callable[[State], int]]] = {}
        self._arguments: list[ArgumentArgs] = []
        self._groups: list[tuple[Any, dict[str, Any], list[tuple[dict[str, Any], list[ArgumentArgs]]]]] = []
        super().__init__(*args, **kwargs)
        if root is True:
            self._add_base_options()
        if add_cmd is True:
            msg = "tox command to execute (by default legacy)"
            self._cmd: Any | None = self.add_subparsers(title="subcommands", description=msg, dest="command")
            self._cmd.required = False
            self._cmd.default = "legacy"
        else:
            self._cmd = None

    def add_command(
        self,
        cmd: str,
        aliases: Sequence[str],
        help_msg: str,
        handler: Callable[[State], int],
    ) -> ArgumentParser:
        if self._cmd is None:
            msg = "no sub-command group allowed"
            raise RuntimeError(msg)
        sub_parser: ToxParser = self._cmd.add_parser(
            cmd,
            help=help_msg,
            aliases=aliases,
            formatter_class=HelpFormatter,
            file_config=self.file_config,
        )
        sub_parser.of_cmd = cmd  # mark it as parser for a sub-command
        content = sub_parser, handler
        self.handlers[cmd] = content
        for alias in aliases:
            self.handlers[alias] = content
        for args, of_type, kwargs in self._arguments:
            sub_parser.add_argument(*args, of_type=of_type, **kwargs)
        for args, kwargs, excl in self._groups:
            group = sub_parser.add_argument_group(*args, **kwargs)
            for e_kwargs, arguments in excl:
                excl_group = group.add_mutually_exclusive_group(**e_kwargs)
                for a_args, _, a_kwargs in arguments:
                    excl_group.add_argument(*a_args, **a_kwargs)
        return sub_parser

    def add_argument_group(self, *args: Any, **kwargs: Any) -> Any:
        result = super().add_argument_group(*args, **kwargs)
        if self.of_cmd is None and args not in (("positional arguments",), ("optional arguments",)):

            def add_mutually_exclusive_group(**e_kwargs: Any) -> Any:
                def add_argument(*a_args: str, of_type: type[Any] | None = None, **a_kwargs: Any) -> Action:
                    res_args: Action = prev_add_arg(*a_args, **a_kwargs)  # type: ignore[has-type]
                    arguments.append((a_args, of_type, a_kwargs))
                    return res_args

                arguments: list[ArgumentArgs] = []
                excl.append((e_kwargs, arguments))
                res_excl = prev_excl(**kwargs)
                prev_add_arg = res_excl.add_argument
                res_excl.add_argument = add_argument  # type: ignore[method-assign]
                return res_excl

            prev_excl = result.add_mutually_exclusive_group
            result.add_mutually_exclusive_group = add_mutually_exclusive_group  # type: ignore[method-assign]
            excl: list[tuple[dict[str, Any], list[ArgumentArgs]]] = []
            self._groups.append((args, kwargs, excl))
        return result

    def add_argument(self, *args: str, of_type: type[Any] | None = None, **kwargs: Any) -> Action:
        result = super().add_argument(*args, **kwargs)
        if self.of_cmd is None and result.dest != "help":
            self._arguments.append((args, of_type, kwargs))
            if hasattr(self, "_cmd") and self._cmd is not None and hasattr(self._cmd, "choices"):
                for parser in {id(v): v for k, v in self._cmd.choices.items()}.values():
                    parser.add_argument(*args, of_type=of_type, **kwargs)
        if of_type is not None:
            result.of_type = of_type  # type: ignore[attr-defined]
        return result

    @classmethod
    def base(cls: type[ToxParserT]) -> ToxParserT:
        return cls(add_help=False, root=True)

    @classmethod
    def core(cls: type[ToxParserT]) -> ToxParserT:
        return cls(
            prog=NAME,
            formatter_class=HelpFormatter,
            add_cmd=True,
            root=True,
            description="create and set up environments to run command(s) in them",
        )

    def _add_base_options(self) -> None:
        """Argument options that always make sense."""
        add_core_arguments(self)
        self.fix_defaults()

    def parse_known_args(  # type: ignore[override]
        self,
        args: Sequence[str] | None = None,
        namespace: Parsed | None = None,
    ) -> tuple[Parsed, list[str]]:
        if args is None:
            args = sys.argv[1:]
        cmd_at: int | None = None
        if self._cmd is not None and args:
            for at, arg in enumerate(args):
                if arg in self._cmd.choices:
                    cmd_at = at
                    break
            else:
                cmd_at = None
        if cmd_at is not None:  # if we found a command move it to the start
            args = args[cmd_at], *args[:cmd_at], *args[cmd_at + 1 :]
        elif args not in (("--help",), ("-h",)) and (self._cmd is not None and "legacy" in self._cmd.choices):
            # on help no mangling needed, and we also want to insert once we have legacy to insert
            args = "legacy", *args
        result = Parsed() if namespace is None else namespace
        _, args = super().parse_known_args(args, namespace=result)
        return result, args


def add_verbosity_flags(parser: ArgumentParser) -> None:
    from tox.report import LEVELS

    level_map = "|".join(f"{c}={logging.getLevelName(level)}" for c, level in sorted(LEVELS.items()))
    verbosity_group = parser.add_argument_group("verbosity")
    verbosity_group.description = (
        f"every -v increases, every -q decreases verbosity level, "
        f"default {logging.getLevelName(LEVELS[DEFAULT_VERBOSITY])}, map {level_map}"
    )
    verbosity = verbosity_group.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-v",
        "--verbose",
        action="count",
        dest="verbose",
        help="increase verbosity",
        default=DEFAULT_VERBOSITY,
    )
    verbosity.add_argument("-q", "--quiet", action="count", dest="quiet", help="decrease verbosity", default=0)


def add_color_flags(parser: ArgumentParser) -> None:
    converter = StrConvert()
    if os.environ.get("NO_COLOR", ""):
        color = "no"
    elif converter.to_bool(os.environ.get("FORCE_COLOR", "")):
        color = "yes"
    elif os.environ.get("TERM", "") == "dumb":
        color = "no"
    else:
        color = "yes" if sys.stdout.isatty() else "no"

    parser.add_argument(
        "--colored",
        default=color,
        choices=["yes", "no"],
        help="should output be enriched with colors, default is yes unless TERM=dumb or NO_COLOR is defined.",
    )


def add_exit_and_dump_after(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--exit-and-dump-after",
        dest="exit_and_dump_after",
        metavar="seconds",
        default=0,
        type=int,
        help="dump tox threads after n seconds and exit the app - useful to debug when tox hangs, 0 means disabled",
    )


def add_core_arguments(parser: ArgumentParser) -> None:
    add_color_flags(parser)
    add_verbosity_flags(parser)
    add_exit_and_dump_after(parser)
    parser.add_argument(
        "-c",
        "--conf",
        dest="config_file",
        metavar="file",
        default=None,
        type=Path,
        of_type=Optional[Path],
        help="configuration file/folder for tox (if not specified will discover one)",
    )
    parser.add_argument(
        "--workdir",
        dest="work_dir",
        metavar="dir",
        default=None,
        type=Path,
        of_type=Optional[Path],
        help="tox working directory (if not specified will be the folder of the config file)",
    )
    parser.add_argument(
        "--root",
        dest="root_dir",
        metavar="dir",
        default=None,
        type=Path,
        of_type=Optional[Path],
        help="project root directory (if not specified will be the folder of the config file)",
    )


__all__ = (
    "DEFAULT_VERBOSITY",
    "Parsed",
    "ToxParser",
    "HelpFormatter",
)
