from __future__ import annotations

import logging
import sys
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from scrapy.commands import BaseRunSpiderCommand
from scrapy.exceptions import UsageError
from scrapy.spiderloader import DummySpiderLoader
from scrapy.utils.spider import iter_spider_classes

if TYPE_CHECKING:
    import argparse
    from os import PathLike
    from types import ModuleType


logger = logging.getLogger(__name__)


def _import_file(filepath: str | PathLike[str]) -> ModuleType:
    abspath = Path(filepath).resolve()
    if abspath.suffix not in {".py", ".pyw"}:
        raise ValueError(f"Not a Python source file: {abspath}")
    dirname = str(abspath.parent)
    sys.path = [dirname, *sys.path]
    try:
        module = import_module(abspath.stem)
    finally:
        sys.path.pop(0)
    return module


class Command(BaseRunSpiderCommand):
    default_settings: ClassVar[dict[str, Any]] = {
        "SPIDER_LOADER_CLASS": DummySpiderLoader
    }

    def syntax(self) -> str:
        return "[options] <spider_file>"

    def short_desc(self) -> str:
        return "Run a spider from a Python file, no project required"

    def long_desc(self) -> str:
        return "Run the spider defined in the given file"

    def add_options(self, parser: argparse.ArgumentParser) -> None:
        super().add_options(parser)
        parser.add_argument(
            "--spider",
            metavar="NAME",
            help="run the spider with this name, if the file defines more than one",
        )

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        if len(args) != 1:
            raise UsageError
        filename = Path(args[0])
        if not filename.exists():
            raise UsageError(f"File not found: {filename}\n")
        try:
            module = _import_file(filename)
        except (ImportError, ValueError) as e:
            raise UsageError(f"Unable to load {str(filename)!r}: {e}\n") from e
        spclasses = list(iter_spider_classes(module))
        if not spclasses:
            raise UsageError(f"No spider found in file: {filename}\n")
        if opts.spider:
            try:
                spidercls = next(c for c in spclasses if c.name == opts.spider)
            except StopIteration:
                raise UsageError(
                    f"No spider named {opts.spider!r} found in file: {filename}\n"
                ) from None
        else:
            spidercls = spclasses[-1]
            if len(spclasses) > 1:
                names = ", ".join(repr(c.name) for c in spclasses)
                logger.warning(
                    f"{filename} defines more than one spider ({names}), running "
                    f"{spidercls.name!r}. Use --spider to run a different one."
                )

        assert self.crawler_process
        self.crawler_process.crawl(self._create_crawler(spidercls), **opts.spargs)
        self.crawler_process.start()

        if self.crawler_process.bootstrap_failed:
            self.exitcode = 1
