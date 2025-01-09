from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

from scrapy.commands import BaseRunSpiderCommand
from scrapy.exceptions import UsageError
from scrapy.utils.spider import iter_spider_classes

if TYPE_CHECKING:
    import argparse
    from os import PathLike
    from types import ModuleType


def _import_file(filepath: str | PathLike[str]) -> ModuleType:
    abspath = Path(filepath).resolve()
    if abspath.suffix not in (".py", ".pyw"):
        raise ValueError(f"Not a Python source file: {abspath}")
    dirname = str(abspath.parent)
    sys.path = [dirname, *sys.path]
    try:
        module = import_module(abspath.stem)
    finally:
        sys.path.pop(0)
    return module


class Command(BaseRunSpiderCommand):
    requires_project = False
    default_settings = {"SPIDER_LOADER_WARN_ONLY": True}

    def syntax(self) -> str:
        return "[options] <spider_file>"

    def short_desc(self) -> str:
        return "Run a self-contained spider (without creating a project)"

    def long_desc(self) -> str:
        return "Run the spider defined in the given file"

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        if len(args) != 1:
            raise UsageError
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

        assert self.crawler_process
        self.crawler_process.crawl(spidercls, **opts.spargs)
        self.crawler_process.start()

        if self.crawler_process.bootstrap_failed:
            self.exitcode = 1
