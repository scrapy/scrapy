"""
Base class for Scrapy commands
"""

from __future__ import annotations

import argparse
import builtins
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from twisted.python import failure

from scrapy.exceptions import UsageError
from scrapy.utils.conf import arglist_to_dict, feed_process_params_from_cli

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scrapy.crawler import Crawler, CrawlerProcess


class ScrapyCommand:
    requires_project: bool = False
    crawler_process: CrawlerProcess | None = None

    # default settings to be used for this command instead of global defaults
    default_settings: dict[str, Any] = {}

    exitcode: int = 0

    def __init__(self) -> None:
        self.settings: Any = None  # set in scrapy.cmdline

    def set_crawler(self, crawler: Crawler) -> None:
        if hasattr(self, "_crawler"):
            raise RuntimeError("crawler already set")
        self._crawler: Crawler = crawler

    def syntax(self) -> str:
        """
        Command syntax (preferably one-line). Do not include command name.
        """
        return ""

    def short_desc(self) -> str:
        """
        A short description of the command
        """
        return ""

    def long_desc(self) -> str:
        """A long description of the command. Return short description when not
        available. It cannot contain newlines since contents will be formatted
        by optparser which removes newlines and wraps text.
        """
        return self.short_desc()

    def help(self) -> str:
        """An extensive help for the command. It will be shown when using the
        "help" command. It can contain newlines since no post-formatting will
        be applied to its contents.
        """
        return self.long_desc()

    def add_options(self, parser: argparse.ArgumentParser) -> None:
        """
        Populate option parse with options available for this command
        """
        group = parser.add_argument_group(title="Global Options")
        group.add_argument(
            "--logfile", metavar="FILE", help="log file. if omitted stderr will be used"
        )
        group.add_argument(
            "-L",
            "--loglevel",
            metavar="LEVEL",
            default=None,
            help=f"log level (default: {self.settings['LOG_LEVEL']})",
        )
        group.add_argument(
            "--nolog", action="store_true", help="disable logging completely"
        )
        group.add_argument(
            "--profile",
            metavar="FILE",
            default=None,
            help="write python cProfile stats to FILE",
        )
        group.add_argument("--pidfile", metavar="FILE", help="write process ID to FILE")
        group.add_argument(
            "-s",
            "--set",
            action="append",
            default=[],
            metavar="NAME=VALUE",
            help="set/override setting (may be repeated)",
        )
        group.add_argument("--pdb", action="store_true", help="enable pdb on failure")

    def process_options(self, args: list[str], opts: argparse.Namespace) -> None:
        try:
            self.settings.setdict(arglist_to_dict(opts.set), priority="cmdline")
        except ValueError:
            raise UsageError("Invalid -s value, use -s NAME=VALUE", print_help=False)

        if opts.logfile:
            self.settings.set("LOG_ENABLED", True, priority="cmdline")
            self.settings.set("LOG_FILE", opts.logfile, priority="cmdline")

        if opts.loglevel:
            self.settings.set("LOG_ENABLED", True, priority="cmdline")
            self.settings.set("LOG_LEVEL", opts.loglevel, priority="cmdline")

        if opts.nolog:
            self.settings.set("LOG_ENABLED", False, priority="cmdline")

        if opts.pidfile:
            Path(opts.pidfile).write_text(
                str(os.getpid()) + os.linesep, encoding="utf-8"
            )

        if opts.pdb:
            failure.startDebugMode()

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        """
        Entry point for running commands
        """
        raise NotImplementedError


class BaseRunSpiderCommand(ScrapyCommand):
    """
    Common class used to share functionality between the crawl, parse and runspider commands
    """

    def add_options(self, parser: argparse.ArgumentParser) -> None:
        super().add_options(parser)
        parser.add_argument(
            "-a",
            dest="spargs",
            action="append",
            default=[],
            metavar="NAME=VALUE",
            help="set spider argument (may be repeated)",
        )
        parser.add_argument(
            "-o",
            "--output",
            metavar="FILE",
            action="append",
            help="append scraped items to the end of FILE (use - for stdout),"
            " to define format set a colon at the end of the output URI (i.e. -o FILE:FORMAT)",
        )
        parser.add_argument(
            "-O",
            "--overwrite-output",
            metavar="FILE",
            action="append",
            help="dump scraped items into FILE, overwriting any existing file,"
            " to define format set a colon at the end of the output URI (i.e. -O FILE:FORMAT)",
        )

    def process_options(self, args: list[str], opts: argparse.Namespace) -> None:
        super().process_options(args, opts)
        try:
            opts.spargs = arglist_to_dict(opts.spargs)
        except ValueError:
            raise UsageError("Invalid -a value, use -a NAME=VALUE", print_help=False)
        if opts.output or opts.overwrite_output:
            feeds = feed_process_params_from_cli(
                self.settings,
                opts.output,
                overwrite_output=opts.overwrite_output,
            )
            self.settings.set("FEEDS", feeds, priority="cmdline")


class ScrapyHelpFormatter(argparse.HelpFormatter):
    """
    Help Formatter for scrapy command line help messages.
    """

    def __init__(
        self,
        prog: str,
        indent_increment: int = 2,
        max_help_position: int = 24,
        width: int | None = None,
    ):
        super().__init__(
            prog,
            indent_increment=indent_increment,
            max_help_position=max_help_position,
            width=width,
        )

    def _join_parts(self, part_strings: Iterable[str]) -> str:
        # scrapy.commands.list shadows builtins.list
        parts = self.format_part_strings(builtins.list(part_strings))
        return super()._join_parts(parts)

    def format_part_strings(self, part_strings: list[str]) -> list[str]:
        """
        Underline and title case command line help message headers.
        """
        if part_strings and part_strings[0].startswith("usage: "):
            part_strings[0] = "Usage\n=====\n  " + part_strings[0][len("usage: ") :]
        headings = [
            i for i in range(len(part_strings)) if part_strings[i].endswith(":\n")
        ]
        for index in headings[::-1]:
            char = "-" if "Global Options" in part_strings[index] else "="
            part_strings[index] = part_strings[index][:-2].title()
            underline = "".join(["\n", (char * len(part_strings[index])), "\n"])
            part_strings.insert(index + 1, underline)
        return part_strings
