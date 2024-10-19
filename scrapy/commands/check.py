import argparse
import time
from collections import defaultdict
from unittest import TextTestResult as _TextTestResult
from unittest import TextTestRunner

from scrapy.commands import ScrapyCommand
from scrapy.contracts import ContractsManager
from scrapy.utils.conf import build_component_list
from scrapy.utils.misc import load_object, set_environ


class TextTestResult(_TextTestResult):
    def printSummary(self, start: float, stop: float) -> None:
        write = self.stream.write
        writeln = self.stream.writeln

        run = self.testsRun
        plural = "s" if run != 1 else ""

        writeln(self.separator2)
        writeln(f"Ran {run} contract{plural} in {stop - start:.3f}s")
        writeln()

        infos = []
        if not self.wasSuccessful():
            write("FAILED")
            failed, errored = map(len, (self.failures, self.errors))
            if failed:
                infos.append(f"failures={failed}")
            if errored:
                infos.append(f"errors={errored}")
        else:
            write("OK")

        if infos:
            writeln(f" ({', '.join(infos)})")
        else:
            write("\n")


class Command(ScrapyCommand):
    requires_project = True
    default_settings = {"LOG_ENABLED": False}

    def syntax(self) -> str:
        return "[options] <spider>"

    def short_desc(self) -> str:
        return "Check spider contracts"

    def add_options(self, parser: argparse.ArgumentParser) -> None:
        super().add_options(parser)
        parser.add_argument(
            "-l",
            "--list",
            dest="list",
            action="store_true",
            help="only list contracts, without checking them",
        )
        parser.add_argument(
            "-v",
            "--verbose",
            dest="verbose",
            default=False,
            action="store_true",
            help="print contract tests for all spiders",
        )

    def run(self, args: list[str], opts: argparse.Namespace) -> None:
        # load contracts
        contracts = build_component_list(self.settings.getwithbase("SPIDER_CONTRACTS"))
        conman = ContractsManager(load_object(c) for c in contracts)
        runner = TextTestRunner(verbosity=2 if opts.verbose else 1)
        result = TextTestResult(runner.stream, runner.descriptions, runner.verbosity)

        # contract requests
        contract_reqs = defaultdict(list)

        assert self.crawler_process
        spider_loader = self.crawler_process.spider_loader

        with set_environ(SCRAPY_CHECK="true"):
            for spidername in args or spider_loader.list():
                spidercls = spider_loader.load(spidername)
                spidercls.start_requests = lambda s: conman.from_spider(s, result)  # type: ignore[assignment,method-assign,return-value]

                tested_methods = conman.tested_methods_from_spidercls(spidercls)
                if opts.list:
                    for method in tested_methods:
                        contract_reqs[spidercls.name].append(method)
                elif tested_methods:
                    self.crawler_process.crawl(spidercls)

            # start checks
            if opts.list:
                for spider, methods in sorted(contract_reqs.items()):
                    if not methods and not opts.verbose:
                        continue
                    print(spider)
                    for method in sorted(methods):
                        print(f"  * {method}")
            else:
                start = time.time()
                self.crawler_process.start()
                stop = time.time()

                result.printErrors()
                result.printSummary(start, stop)
                self.exitcode = int(not result.wasSuccessful())
