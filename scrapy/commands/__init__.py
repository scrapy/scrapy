"""
Base class for Scrapy commands
"""

from __future__ import annotations

import argparse
import builtins
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from twisted.python import failure

from scrapy.exceptions import UsageError
from scrapy.utils.conf import arglist_to_dict, feed_process_params_from_cli

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scrapy.crawler import Crawler, CrawlerProcessBase
    from scrapy.settings import Settings


class ScrapyCommand(ABC):
    """
    Base class for implementing Scrapy commands.

    This class provides the foundation for creating custom Scrapy commands. When creating
    a custom command, inherit from this class and implement the required abstract methods.

    Class Attributes:
        requires_project (bool): Set to True if the command requires a Scrapy project
            to run. Commands that require access to project-specific settings, spiders,
            or other project components should set this to True. Default: False.
        
        requires_crawler_process (bool): Set to True if the command needs access to
            a CrawlerProcess instance. Commands that need to run spiders or crawls
            should set this to True. Default: True.
        
        default_settings (dict[str, Any]): Default settings to use for this command
            instead of global defaults. This allows commands to override specific
            settings without affecting the global configuration. Default: {}.

    Instance Attributes:
        crawler_process (CrawlerProcessBase | None): The crawler process instance,
            set automatically by scrapy.cmdline when the command is run.
        
        settings (Settings | None): The settings instance for this command,
            set automatically by scrapy.cmdline when the command is run.
        
        exitcode (int): The exit code to return when the command finishes.
            Set this to a non-zero value to indicate an error. Default: 0.

    Example:
        To create a custom command that lists all available spiders::

            from scrapy.commands import ScrapyCommand

            class Command(ScrapyCommand):
                requires_project = True
                requires_crawler_process = False
                default_settings = {"LOG_ENABLED": False}

                def short_desc(self):
                    return "List available spiders"

                def run(self, args, opts):
                    from scrapy.spiderloader import get_spider_loader
                    spider_loader = get_spider_loader(self.settings)
                    for spider_name in sorted(spider_loader.list()):
                        print(spider_name)
    """
    requires_project: bool = False
    requires_crawler_process: bool = True
    crawler_process: CrawlerProcessBase | None = None  # set in scrapy.cmdline

    # default settings to be used for this command instead of global defaults
    default_settings: dict[str, Any] = {}

    exitcode: int = 0

    def __init__(self) -> None:
        self.settings: Settings | None = None  # set in scrapy.cmdline

    def set_crawler(self, crawler: Crawler) -> None:
        if hasattr(self, "_crawler"):
            raise RuntimeError("crawler already set")
        self._crawler: Crawler = crawler

    def syntax(self) -> str:
        """
        Return the command syntax (preferably one-line). Do not include command name.
        
        This should describe the arguments and options that the command accepts.
        
        Returns:
            str: A string describing the command syntax, e.g., "[options] <spider>"
            
        Example:
            For a command that takes a spider name::
            
                def syntax(self):
                    return "[options] <spider>"
        """
        return ""

    @abstractmethod
    def short_desc(self) -> str:
        """
        Return a short description of the command.
        
        This method must be implemented by subclasses. The description should be
        concise and explain what the command does in a few words.
        
        Returns:
            str: A brief description of the command's purpose.
            
        Example:
            def short_desc(self):
                return "Run a spider"
        """
        return ""

    def long_desc(self) -> str:
        """
        Return a long description of the command.
        
        Override this method to provide a more detailed description of the command.
        The description cannot contain newlines since contents will be formatted
        by optparser which removes newlines and wraps text.
        
        Returns:
            str: A detailed description of the command. Defaults to short_desc().
            
        Note:
            If you need to include newlines in your help text, use the help() method instead.
        """
        return self.short_desc()

    def help(self) -> str:
        """
        Return extensive help text for the command.
        
        This method provides detailed help that will be shown when using the
        "help" command. Unlike long_desc(), this can contain newlines since
        no post-formatting will be applied to its contents.
        
        Returns:
            str: Detailed help text for the command. Defaults to long_desc().
            
        Example:
            def help(self):
                return '''Run a spider by name.
            
            This command starts a spider by its name and runs it until completion.
            You can pass arguments to the spider using -a option.
            
            Examples:
              scrapy crawl myspider
              scrapy crawl myspider -a domain=example.com
            '''
        """
        return self.long_desc()

    def add_options(self, parser: argparse.ArgumentParser) -> None:
        """
        Add command-specific options to the argument parser.
        
        Override this method to add custom command-line options for your command.
        The base implementation adds common global options like --logfile, --loglevel, etc.
        
        Args:
            parser (argparse.ArgumentParser): The argument parser to add options to.
            
        Example:
            def add_options(self, parser):
                super().add_options(parser)
                parser.add_argument('--custom-option', help='Custom option for this command')
        """
        assert self.settings is not None
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
        """
        Process command-line options after they have been parsed.
        
        Override this method to handle custom options added in add_options().
        The base implementation processes common global options.
        
        Args:
            args (list[str]): Command-line arguments that were not parsed as options.
            opts (argparse.Namespace): Parsed command-line options.
            
        Example:
            def process_options(self, args, opts):
                super().process_options(args, opts)
                if opts.custom_option:
                    self.settings.set('CUSTOM_SETTING', opts.custom_option)
        """
        assert self.settings is not None
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

    @abstractmethod
    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        """
        Execute the command logic.
        
        This method must be implemented by subclasses and contains the main
        logic for the command.
        
        Args:
            args (list[str]): Command-line arguments that were not parsed as options.
            opts (argparse.Namespace): Parsed command-line options.
            
        Example:
            def run(self, args, opts):
                if len(args) < 1:
                    raise UsageError("Missing required argument")
                spider_name = args[0]
                # Command logic here...
        """
        raise NotImplementedError


class BaseRunSpiderCommand(ScrapyCommand):
    """
    Base class for commands that run spiders.
    
    This class extends ScrapyCommand with functionality common to commands that need to
    run spiders, such as crawl, parse, and runspider. It adds spider argument handling
    and output options.
    
    Additional Options Added:
        -a NAME=VALUE: Set spider argument (may be repeated)
        -o FILE: Append scraped items to the end of FILE
        -O FILE: Dump scraped items into FILE, overwriting any existing file
        
    Example:
        For a command that runs a specific spider with custom behavior::
        
            class Command(BaseRunSpiderCommand):
                requires_project = True
                
                def short_desc(self):
                    return "Run a spider with custom settings"
                
                def run(self, args, opts):
                    spider_name = args[0]
                    self.crawler_process.crawl(spider_name, **opts.spargs)
                    self.crawler_process.start()
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
            assert self.settings is not None
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
