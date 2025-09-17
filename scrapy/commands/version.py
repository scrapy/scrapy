import argparse

from rich.table import Table

import scrapy
from scrapy.commands import ScrapyCommand
from scrapy.utils.console import get_console
from scrapy.utils.versions import get_versions


class Command(ScrapyCommand):
    requires_crawler_process = False
    default_settings = {"LOG_ENABLED": False}

    def syntax(self) -> str:
        return "[-v]"

    def short_desc(self) -> str:
        return "Print Scrapy version"

    def add_options(self, parser: argparse.ArgumentParser) -> None:
        super().add_options(parser)
        parser.add_argument(
            "--verbose",
            "-v",
            dest="verbose",
            action="store_true",
            help="also display twisted/python/platform info (useful for bug reports)",
        )

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        console = get_console(use_stderr=False)

        if opts.verbose:
            versions = get_versions()

            # Create a rich table for versions
            table = Table(title="Software Versions", show_header=True, header_style="bold magenta")
            table.add_column("Package", style="cyan", no_wrap=True)
            table.add_column("Version", style="green")

            for name, version in versions:
                table.add_row(name, str(version))

            console.print(table)
        else:
            console.print(f"[bold green]Scrapy[/bold green] [cyan]{scrapy.__version__}[/cyan]")
