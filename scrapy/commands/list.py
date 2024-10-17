from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy.commands import ScrapyCommand

if TYPE_CHECKING:
    import argparse


class Command(ScrapyCommand):
    requires_project = True
    default_settings = {"LOG_ENABLED": False}

    def short_desc(self) -> str:
        return "List available spiders"

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        assert self.crawler_process
        for s in sorted(self.crawler_process.spider_loader.list()):
            print(s)
