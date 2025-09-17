import argparse
import json

from scrapy.commands import ScrapyCommand
from scrapy.settings import BaseSettings
from scrapy.utils.console import get_console


class Command(ScrapyCommand):
    requires_crawler_process = False
    default_settings = {"LOG_ENABLED": False}

    def syntax(self) -> str:
        return "[options]"

    def short_desc(self) -> str:
        return "Get settings values"

    def add_options(self, parser: argparse.ArgumentParser) -> None:
        super().add_options(parser)
        parser.add_argument(
            "--get", dest="get", metavar="SETTING", help="print raw setting value"
        )
        parser.add_argument(
            "--getbool",
            dest="getbool",
            metavar="SETTING",
            help="print setting value, interpreted as a boolean",
        )
        parser.add_argument(
            "--getint",
            dest="getint",
            metavar="SETTING",
            help="print setting value, interpreted as an integer",
        )
        parser.add_argument(
            "--getfloat",
            dest="getfloat",
            metavar="SETTING",
            help="print setting value, interpreted as a float",
        )
        parser.add_argument(
            "--getlist",
            dest="getlist",
            metavar="SETTING",
            help="print setting value, interpreted as a list",
        )

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        assert self.settings is not None
        settings = self.settings
        console = get_console(use_stderr=False)

        if opts.get:
            s = settings.get(opts.get)
            if isinstance(s, BaseSettings):
                console.print_json(json.dumps(s.copy_to_dict()))
            else:
                console.print(f"[info]{opts.get}[/info]: {s}")
        elif opts.getbool:
            value = settings.getbool(opts.getbool)
            console.print(f"[info]{opts.getbool}[/info]: [number]{value}[/number]")
        elif opts.getint:
            value = settings.getint(opts.getint)
            console.print(f"[info]{opts.getint}[/info]: [number]{value}[/number]")
        elif opts.getfloat:
            value = settings.getfloat(opts.getfloat)
            console.print(f"[info]{opts.getfloat}[/info]: [number]{value}[/number]")
        elif opts.getlist:
            value = settings.getlist(opts.getlist)
            console.print(f"[info]{opts.getlist}[/info]: {value}")
