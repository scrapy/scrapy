from __future__ import print_function
import time
import sys
from collections import defaultdict
from unittest import TextTestRunner, TextTestResult as _TextTestResult

from scrapy.command import ScrapyCommand
from scrapy.contracts import ContractsManager
from scrapy.utils.misc import load_object
from scrapy.utils.conf import build_component_list


class TextTestResult(_TextTestResult):
    def printSummary(self, start, stop):
        write = self.stream.write
        writeln = self.stream.writeln

        run = self.testsRun
        plural = "s" if run != 1 else ""

        writeln(self.separator2)
        writeln("Ran %d contract%s in %.3fs" % (run, plural, stop - start))
        writeln()

        infos = []
        if not self.wasSuccessful():
            write("FAILED")
            failed, errored = map(len, (self.failures, self.errors))
            if failed:
                infos.append("failures=%d" % failed)
            if errored:
                infos.append("errors=%d" % errored)
        else:
            write("OK")

        if infos:
            writeln(" (%s)" % (", ".join(infos),))
        else:
            write("\n")


class Command(ScrapyCommand):
    requires_project = True
    default_settings = {'LOG_ENABLED': False}

    def syntax(self):
        return "[options] <spider>"

    def short_desc(self):
        return "Check spider contracts"

    def add_options(self, parser):
        ScrapyCommand.add_options(self, parser)
        parser.add_option("-l", "--list", dest="list", action="store_true",
                          help="only list contracts, without checking them")
        parser.add_option("-v", "--verbose", dest="verbose", default=False, action='store_true',
                          help="print contract tests for all spiders")

    def run(self, args, opts):
        # load contracts
        contracts = build_component_list(
            self.settings['SPIDER_CONTRACTS_BASE'],
            self.settings['SPIDER_CONTRACTS'],
        )
        conman = ContractsManager([load_object(c) for c in contracts])
        runner = TextTestRunner(verbosity=2 if opts.verbose else 1)
        result = TextTestResult(runner.stream, runner.descriptions, runner.verbosity)

        # contract requests
        contract_reqs = defaultdict(list)

        spman_cls = load_object(self.settings['SPIDER_MANAGER_CLASS'])
        spiders = spman_cls.from_settings(self.settings)

        for spider in args or spiders.list():
            spider = spiders.create(spider)
            requests = self.get_requests(spider, conman, result)
            contract_reqs[spider.name] = []

            if opts.list:
                for req in requests:
                    contract_reqs[spider.name].append(req.callback.__name__)
            elif requests:
                crawler = self.crawler_process.create_crawler(spider.name)
                crawler.crawl(spider, requests)

        # start checks
        if opts.list:
            for spider, methods in sorted(contract_reqs.iteritems()):
                if not methods and not opts.verbose:
                    continue
                print(spider)
                for method in sorted(methods):
                    print('  * %s' % method)
        else:
            start = time.time()
            self.crawler_process.start()
            stop = time.time()

            result.printErrors()
            result.printSummary(start, stop)
            self.exitcode = int(not result.wasSuccessful())

    def get_requests(self, spider, conman, result):
        requests = []

        for key, value in vars(type(spider)).items():
            if callable(value) and value.__doc__:
                bound_method = value.__get__(spider, type(spider))
                request = conman.from_method(bound_method, result)

                if request:
                    requests.append(request)

        return requests
