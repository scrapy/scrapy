import argparse
import json

from scrapy.commands import ScrapyCommand
from scrapy.settings import BaseSettings


class Command(ScrapyCommand):
    requires_project = False
    default_settings = {"LOG_ENABLED": False, "SPIDER_LOADER_WARN_ONLY": True}

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
        assert self.crawler_process
        settings = self.crawler_process.settings
        if opts.get:
            s = settings.get(opts.get)
            if isinstance(s, BaseSettings):
                print(json.dumps(s.copy_to_dict()))
            else:
                print(s)
        elif opts.getbool:
            print(settings.getbool(opts.getbool))
        elif opts.getint:
            print(settings.getint(opts.getint))
        elif opts.getfloat:
            print(settings.getfloat(opts.getfloat))
        elif opts.getlist:
            print(settings.getlist(opts.getlist))
