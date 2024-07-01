import argparse
import json
import os
from pathlib import Path
from typing import List

from scrapy.commands import ScrapyCommand
from scrapy.settings import BaseSettings

branch_coverage_run = {
    "run_1": False,
    "run_1-1": False,
    "run_1-2": False,
    "run_2": False,
    "run_3": False,
    "run_4": False,
    "run_5": False,
    "run_6_default": False,
}


def write_coverage_run_to_file():
    project_dir = Path(__file__).resolve().parent.parent.parent
    output_file = os.path.join(project_dir, "branch_coverage_run.txt")
    coverage_percentage = (
        sum(branch_coverage_run.values()) / len(branch_coverage_run)
    ) * 100
    with open(output_file, "w", encoding="utf-8") as f:
        for branch, executed in branch_coverage_run.items():
            f.write(f"{branch} has been {'executed' if executed else 'missed'}\n")
        f.write(f"Branch coverage: {coverage_percentage:.2f}%\n")


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

    def run(self, args: List[str], opts: argparse.Namespace) -> None:
        assert self.crawler_process
        settings = self.crawler_process.settings
        if opts.get:
            branch_coverage_run["run_1"] = True
            s = settings.get(opts.get)
            if isinstance(s, BaseSettings):
                branch_coverage_run["run_1-1"] = True
                print(json.dumps(s.copy_to_dict()))
            else:
                branch_coverage_run["run_1-2"] = True
                print(s)
        elif opts.getbool:
            branch_coverage_run["run_2"] = True
            print(settings.getbool(opts.getbool))
        elif opts.getint:
            branch_coverage_run["run_3"] = True
            print(settings.getint(opts.getint))
        elif opts.getfloat:
            branch_coverage_run["run_4"] = True
            print(settings.getfloat(opts.getfloat))
        elif opts.getlist:
            branch_coverage_run["run_5"] = True
            print(settings.getlist(opts.getlist))
        else:
            branch_coverage_run["run_6_default"] = True
        write_coverage_run_to_file()
