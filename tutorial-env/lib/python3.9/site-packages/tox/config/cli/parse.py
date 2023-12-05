"""This module pulls together this package: create and parse CLI arguments for tox."""
from __future__ import annotations

import os
from contextlib import redirect_stderr
from pathlib import Path
from typing import TYPE_CHECKING, Callable, NamedTuple, Sequence, cast

from tox.config.source import Source, discover_source
from tox.report import ToxHandler, setup_report

from .parser import Parsed, ToxParser

if TYPE_CHECKING:
    from tox.session.state import State


class Options(NamedTuple):
    parsed: Parsed
    pos_args: Sequence[str] | None
    source: Source
    cmd_handlers: dict[str, Callable[[State], int]]
    log_handler: ToxHandler


def get_options(*args: str) -> Options:
    pos_args: tuple[str, ...] | None = None
    try:  # remove positional arguments passed to parser if specified, they are pulled directly from sys.argv
        pos_arg_at = args.index("--")
    except ValueError:
        pass
    else:
        pos_args = tuple(args[pos_arg_at + 1 :])
        args = args[:pos_arg_at]

    guess_verbosity, log_handler, source = _get_base(args)
    parsed, cmd_handlers = _get_all(args)
    if guess_verbosity != parsed.verbosity:
        log_handler.update_verbosity(parsed.verbosity)
    return Options(parsed, pos_args, source, cmd_handlers, log_handler)


def _get_base(args: Sequence[str]) -> tuple[int, ToxHandler, Source]:
    """First just load the base options (verbosity+color) to setup the logging framework."""
    tox_parser = ToxParser.base()
    parsed = Parsed()
    try:
        with Path(os.devnull).open("w") as file_handler, redirect_stderr(file_handler):
            tox_parser.parse_known_args(args, namespace=parsed)
    except SystemExit:
        ...  # ignore parse errors, such as -va raises ignored explicit argument 'a'
    guess_verbosity = parsed.verbosity
    handler = setup_report(guess_verbosity, parsed.is_colored)
    from tox.plugin.manager import MANAGER  # load the plugin system right after we set up report

    source = discover_source(parsed.config_file, parsed.root_dir)

    MANAGER.load_plugins(source.path)

    return guess_verbosity, handler, source


def _get_all(args: Sequence[str]) -> tuple[Parsed, dict[str, Callable[[State], int]]]:
    """Parse all the options."""
    tox_parser = _get_parser()
    parsed = cast(Parsed, tox_parser.parse_args(args))
    handlers = {k: p for k, (_, p) in tox_parser.handlers.items()}
    return parsed, handlers


def _get_parser() -> ToxParser:
    tox_parser = ToxParser.core()  # load the core options
    # plus options setup by plugins
    from tox.plugin.manager import MANAGER

    MANAGER.tox_add_option(tox_parser)
    tox_parser.fix_defaults()
    return tox_parser


def _get_parser_doc() -> ToxParser:
    # trigger register of tox env types (during normal run we call this later to handle plugins)
    from tox.plugin.manager import MANAGER  # pragma: no cover

    MANAGER.load_plugins(Path.cwd())

    return _get_parser()  # pragma: no cover


__all__ = (
    "get_options",
    "Options",
)
