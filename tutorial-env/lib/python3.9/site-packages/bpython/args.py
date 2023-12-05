# The MIT License
#
# Copyright (c) 2008 Bob Farrell
# Copyright (c) 2012-2021 Sebastian Ramacher
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

# To gradually migrate to mypy we aren't setting these globally yet
# mypy: disallow_untyped_defs=True
# mypy: disallow_untyped_calls=True

"""
Module to handle command line argument parsing, for all front-ends.
"""

import argparse
from typing import Tuple, List, Optional, NoReturn, Callable
import code
import curtsies
import cwcwidth
import greenlet
import importlib.util
import logging
import os
import pygments
import requests
import sys
import xdg
from pathlib import Path

from . import __version__, __copyright__
from .config import default_config_path, Config
from .translations import _

logger = logging.getLogger(__name__)


class ArgumentParserFailed(ValueError):
    """Raised by the RaisingOptionParser for a bogus commandline."""


class RaisingArgumentParser(argparse.ArgumentParser):
    def error(self, msg: str) -> NoReturn:
        raise ArgumentParserFailed()


def version_banner(base: str = "bpython") -> str:
    return _("{} version {} on top of Python {} {}").format(
        base,
        __version__,
        sys.version.split()[0],
        sys.executable,
    )


def copyright_banner() -> str:
    return _("{} See AUTHORS.rst for details.").format(__copyright__)


Options = Tuple[str, str, Callable[[argparse._ArgumentGroup], None]]


def parse(
    args: Optional[List[str]],
    extras: Optional[Options] = None,
    ignore_stdin: bool = False,
) -> Tuple[Config, argparse.Namespace, List[str]]:
    """Receive an argument list - if None, use sys.argv - parse all args and
    take appropriate action. Also receive optional extra argument: this should
    be a tuple of (title, description, callback)
        title:          The title for the argument group
        description:    A full description of the argument group
        callback:       A callback that adds argument to the argument group

    e.g.:

    def callback(group):
        group.add_argument('-f', action='store_true', dest='f', help='Explode')
        group.add_argument('-l', action='store_true', dest='l', help='Love')

    parse(
        ['-i', '-m', 'foo.py'],
        (
            'Front end-specific options',
            'A full description of what these options are for',
            callback
        ),
    )


    Return a tuple of (config, options, exec_args) wherein "config" is the
    config object either parsed from a default/specified config file or default
    config options, "options" is the parsed options from
    ArgumentParser.parse_args, and "exec_args" are the args (if any) to be parsed
    to the executed file (if any).
    """
    if args is None:
        args = sys.argv[1:]

    parser = RaisingArgumentParser(
        usage=_(
            "Usage: %(prog)s [options] [file [args]]\n"
            "NOTE: If bpython sees an argument it does "
            "not know, execution falls back to the "
            "regular Python interpreter."
        )
    )
    parser.add_argument(
        "--config",
        default=default_config_path(),
        type=Path,
        help=_("Use CONFIG instead of default config file."),
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help=_("Drop to bpython shell after running file instead of exiting."),
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help=_("Don't flush the output to stdout."),
    )
    parser.add_argument(
        "--version",
        "-V",
        action="store_true",
        help=_("Print version and exit."),
    )
    parser.add_argument(
        "--log-level",
        "-l",
        choices=("debug", "info", "warning", "error", "critical"),
        default="error",
        help=_("Set log level for logging"),
    )
    parser.add_argument(
        "--log-output",
        "-L",
        help=_("Log output file"),
    )

    if extras is not None:
        extras_group = parser.add_argument_group(extras[0], extras[1])
        extras[2](extras_group)

    # collect all the remaining arguments into a list
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help=_(
            "File to execute and additional arguments passed on to the executed script."
        ),
    )

    try:
        options = parser.parse_args(args)
    except ArgumentParserFailed:
        # Just let Python handle this
        os.execv(sys.executable, [sys.executable] + args)

    if options.version:
        print(version_banner())
        print(copyright_banner())
        raise SystemExit

    if not ignore_stdin and not (sys.stdin.isatty() and sys.stdout.isatty()):
        # Just let Python handle this
        os.execv(sys.executable, [sys.executable] + args)

    # Configure logging handler
    bpython_logger = logging.getLogger("bpython")
    curtsies_logger = logging.getLogger("curtsies")
    bpython_logger.setLevel(options.log_level.upper())
    curtsies_logger.setLevel(options.log_level.upper())
    if options.log_output:
        handler = logging.FileHandler(filename=options.log_output)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s: %(name)s: %(levelname)s: %(message)s"
            )
        )
        bpython_logger.addHandler(handler)
        curtsies_logger.addHandler(handler)
        bpython_logger.propagate = curtsies_logger.propagate = False
    else:
        bpython_logger.addHandler(logging.NullHandler())
        curtsies_logger.addHandler(logging.NullHandler())

    logger.info("Starting bpython %s", __version__)
    logger.info("Python %s: %s", sys.executable, sys.version_info)
    # versions of required dependencies
    logger.info("curtsies: %s", curtsies.__version__)
    logger.info("cwcwidth: %s", cwcwidth.__version__)
    logger.info("greenlet: %s", greenlet.__version__)
    logger.info("pygments: %s", pygments.__version__)  # type: ignore
    logger.info("pyxdg: %s", xdg.__version__)  # type: ignore
    logger.info("requests: %s", requests.__version__)

    # versions of optional dependencies
    try:
        import pyperclip

        logger.info("pyperclip: %s", pyperclip.__version__)  # type: ignore
    except ImportError:
        logger.info("pyperclip: not available")
    try:
        import jedi

        logger.info("jedi: %s", jedi.__version__)
    except ImportError:
        logger.info("jedi: not available")
    try:
        import watchdog

        logger.info("watchdog: available")
    except ImportError:
        logger.info("watchdog: not available")

    logger.info("environment:")
    for key, value in sorted(os.environ.items()):
        if key.startswith("LC") or key.startswith("LANG") or key == "TERM":
            logger.info("%s: %s", key, value)

    return Config(options.config), options, options.args


def exec_code(
    interpreter: code.InteractiveInterpreter, args: List[str]
) -> None:
    """
    Helper to execute code in a given interpreter, e.g. to implement the behavior of python3 [-i] file.py

    args should be a [faked] sys.argv.
    """
    try:
        with open(args[0]) as sourcefile:
            source = sourcefile.read()
    except OSError as e:
        # print an error and exit (if -i is specified the calling code will continue)
        print(f"bpython: can't open file '{args[0]}: {e}", file=sys.stderr)
        raise SystemExit(e.errno)
    old_argv, sys.argv = sys.argv, args
    sys.path.insert(0, os.path.abspath(os.path.dirname(args[0])))
    spec = importlib.util.spec_from_loader("__main__", loader=None)
    assert spec
    mod = importlib.util.module_from_spec(spec)
    sys.modules["__main__"] = mod
    interpreter.locals.update(mod.__dict__)  # type: ignore  # TODO use a more specific type that has a .locals attribute
    interpreter.locals["__file__"] = args[0]  # type: ignore  # TODO use a more specific type that has a .locals attribute
    interpreter.runsource(source, args[0], "exec")
    sys.argv = old_argv
