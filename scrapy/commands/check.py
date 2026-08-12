import argparse
import asyncio
import time
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable
from typing import Any, ClassVar
from unittest import TestCase, TextTestRunner
from unittest import TextTestResult as _TextTestResult

from twisted.internet.defer import Deferred
from twisted.python.failure import Failure

from scrapy import Spider
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


def _report_crawl_errors(
    crawl: Awaitable[None], spidername: str, result: TextTestResult
) -> None:
    """Make an exception that stops *crawl* before its contracts can run show
    up as an error in *result*, instead of being silently discarded."""

    class CrawlTestCase(TestCase):
        def runTest(self) -> None:
            pass

        def __str__(self) -> str:
            return f"[{spidername}] crawl"

    def report(exception: BaseException) -> None:
        result.addError(
            CrawlTestCase(),
            (type(exception), exception, exception.__traceback__),  # type: ignore[arg-type]
        )

    if isinstance(crawl, Deferred):

        def on_failure(failure: Failure) -> None:
            assert failure.value is not None
            report(failure.value)

        crawl.addErrback(on_failure)
    elif isinstance(crawl, asyncio.Task):

        def on_done(task: asyncio.Task[None]) -> None:
            if not task.cancelled() and (exception := task.exception()) is not None:
                report(exception)

        crawl.add_done_callback(on_done)


class Command(ScrapyCommand):
    requires_project = True
    default_settings: ClassVar[dict[str, Any]] = {"LOG_ENABLED": False}

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
        assert self.settings is not None
        contracts = build_component_list(
            self.settings.get_component_priority_dict_with_base("SPIDER_CONTRACTS")
        )
        conman = ContractsManager(load_object(c) for c in contracts)
        runner = TextTestRunner(verbosity=2 if opts.verbose else 1)
        result = TextTestResult(runner.stream, runner.descriptions, runner.verbosity)

        # contract requests
        contract_reqs = defaultdict(list)

        assert self.crawler_process
        spider_loader = self.crawler_process.spider_loader

        async def start(self: Spider) -> AsyncIterator[Any]:
            for request in conman.from_spider(self, result):
                yield request

        with set_environ(SCRAPY_CHECK="true"):
            for spidername in args or spider_loader.list():
                spidercls = spider_loader.load(spidername)
                spidercls.start = start  # type: ignore[method-assign]

                tested_methods = conman.tested_methods_from_spidercls(spidercls)
                if opts.list:
                    for method in tested_methods:
                        contract_reqs[spidercls.name].append(method)
                elif tested_methods:
                    crawl = self.crawler_process.crawl(spidercls)
                    _report_crawl_errors(crawl, spidercls.name, result)

            # start checks
            if opts.list:
                print(
                    "\n".join(
                        f"{spider}\n"
                        + "\n".join(f"  * {method}" for method in sorted(methods))
                        for spider, methods in sorted(contract_reqs.items())
                        if methods or opts.verbose
                    )
                )
            else:
                start_time = time.monotonic()
                self.crawler_process.start()
                stop = time.monotonic()

                result.printErrors()
                result.printSummary(start_time, stop)
                self.exitcode = int(not result.wasSuccessful())
