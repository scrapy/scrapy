from __future__ import annotations

import argparse
import sys
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

from scrapy.commands import BaseRunSpiderCommand
from scrapy.exceptions import UsageError
from scrapy.utils.spider import iter_spider_classes

if TYPE_CHECKING:
    from os import PathLike
    from types import ModuleType


def _import_file(filepath: str | PathLike[str]) -> ModuleType:
    """Import a Python module from the given file path.

    Args:
        filepath (str | PathLike[str]): The path to the Python file to import.

    Returns:
        ModuleType: The imported Python module.

    Raises:
        ValueError: If the provided file is not a valid Python source file.

    Example:
        >>> module = _import_file('my_spider.py')
    """
    abspath = Path(filepath).resolve()
    if abspath.suffix not in (".py", ".pyw"):
        raise ValueError(f"Not a Python source file: {abspath}")
    dirname = str(abspath.parent)
    sys.path = [dirname] + sys.path
    try:
        module = import_module(abspath.stem)
    finally:
        sys.path.pop(0)
    return module


class Command(BaseRunSpiderCommand):
    """A Scrapy command to run a self-contained spider from a Python file.

    This command runs a spider without needing to create or navigate
    a Scrapy project structure.
    """
    
    requires_project = False
    default_settings = {"SPIDER_LOADER_WARN_ONLY": True}

    def syntax(self) -> str:
        """Return the command-line syntax for this command.

        Returns:
            str: The syntax string for command usage.
        """
        return "[options] <spider_file>"

    def short_desc(self) -> str:
        """Provide a short description of the command.

        Returns:
            str: A brief description of the command.
        """
        return "Run a self-contained spider (without creating a project)"

    def long_desc(self) -> str:
        """Provide a detailed description of the command.

        Returns:
            str: A longer explanation of the command's functionality.
        """
        return "Run the spider defined in the given file"

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        """Execute the command to run a spider from the provided file.

        Args:
            args (list[str]): Command-line arguments passed to the command.
            opts (argparse.Namespace): Parsed options from the command line.

        Raises:
            UsageError: If the arguments are invalid or the file cannot be found.
        """
        if len(args) != 1:
            raise UsageError("A single file argument is required.")
        filename = Path(args[0])
        if not filename.exists():
            raise UsageError(f"File not found: {filename}\n")
        try:
            module = _import_file(filename)
        except (ImportError, ValueError) as e:
            raise UsageError(f"Unable to load {str(filename)!r}: {e}\n")
        spclasses = list(iter_spider_classes(module))
        if not spclasses:
            raise UsageError(f"No spider found in file: {filename}\n")
        spidercls = spclasses.pop()

        assert self.crawler_process, "Crawler process must be initialized."
        self.crawler_process.crawl(spidercls, **opts.spargs)
        self.crawler_process.start()

        if self.crawler_process.bootstrap_failed:
            self.exitcode = 1
