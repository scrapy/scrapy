from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from scrapy.commands import ScrapyCommand
from scrapy.spiderloader import get_spider_loader

if TYPE_CHECKING:
    import argparse


class Command(ScrapyCommand):
    requires_project = True
    requires_crawler_process = False
    default_settings: ClassVar[dict[str, Any]] = {"LOG_ENABLED": False}

    def short_desc(self) -> str:
        return "List available spiders"

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        assert self.settings is not None
        spider_loader = get_spider_loader(self.settings)
        print("\n".join(sorted(spider_loader.list())))
