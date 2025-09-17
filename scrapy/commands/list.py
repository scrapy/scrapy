from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy.commands import ScrapyCommand
from scrapy.spiderloader import get_spider_loader
from scrapy.utils.console import get_console

if TYPE_CHECKING:
    import argparse


class Command(ScrapyCommand):
    requires_project = True
    requires_crawler_process = False
    default_settings = {"LOG_ENABLED": False}

    def short_desc(self) -> str:
        return "List available spiders"

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        assert self.settings is not None
        spider_loader = get_spider_loader(self.settings)
        spiders = list(spider_loader.list())

        try:
            from scrapy.utils.rich_utils import print_spider_list
            print_spider_list(spiders)
        except ImportError:
            # Fallback to simple output
            console = get_console(use_stderr=False)
            if spiders:
                console.print("[info]Available spiders:[/info]")
                for spider in sorted(spiders):
                    console.print(f"  [spider]{spider}[/spider]")
            else:
                console.print("[warning]No spiders found[/warning]")
