import sys
from io import StringIO
from unittest.mock import Mock, PropertyMock, patch

from scrapy.commands.check import Command
from tests.test_commands import CommandTest


class CheckCommandTest(CommandTest):
    command = "check"

    def setUp(self):
        super().setUp()
        self.spider_name = "check_spider"
        self.spider = (self.proj_mod_path / "spiders" / "checkspider.py").resolve()

    def _write_contract(self, contracts, parse_def):
        self.spider.write_text(
            f"""
import scrapy

class CheckSpider(scrapy.Spider):
    name = '{self.spider_name}'
    start_urls = ['data:,']

    def parse(self, response, **cb_kwargs):
        \"\"\"
        @url data:,
        {contracts}
        \"\"\"
        {parse_def}
        """,
            encoding="utf-8",
        )

    def _test_contract(self, contracts="", parse_def="pass"):
        self._write_contract(contracts, parse_def)
        p, out, err = self.proc("check")
        self.assertNotIn("F", out)
        self.assertIn("OK", err)
        self.assertEqual(p.returncode, 0)

    def test_check_returns_requests_contract(self):
        contracts = """
        @returns requests 1
        """
        parse_def = """
        yield scrapy.Request(url='http://next-url.com')
        """
        self._test_contract(contracts, parse_def)

    def test_check_returns_items_contract(self):
        contracts = """
        @returns items 1
        """
        parse_def = """
        yield {'key1': 'val1', 'key2': 'val2'}
        """
        self._test_contract(contracts, parse_def)

    def test_check_cb_kwargs_contract(self):
        contracts = """
        @cb_kwargs {"arg1": "val1", "arg2": "val2"}
        """
        parse_def = """
        if len(cb_kwargs.items()) == 0:
            raise Exception("Callback args not set")
        """
        self._test_contract(contracts, parse_def)

    def test_check_scrapes_contract(self):
        contracts = """
        @scrapes key1 key2
        """
        parse_def = """
        yield {'key1': 'val1', 'key2': 'val2'}
        """
        self._test_contract(contracts, parse_def)

    def test_check_all_default_contracts(self):
        contracts = """
        @returns items 1
        @returns requests 1
        @scrapes key1 key2
        @cb_kwargs {"arg1": "val1", "arg2": "val2"}
        """
        parse_def = """
        yield {'key1': 'val1', 'key2': 'val2'}
        yield scrapy.Request(url='http://next-url.com')
        if len(cb_kwargs.items()) == 0:
            raise Exception("Callback args not set")
        """
        self._test_contract(contracts, parse_def)

    def test_SCRAPY_CHECK_set(self):
        parse_def = """
        import os
        if not os.environ.get('SCRAPY_CHECK'):
            raise Exception('SCRAPY_CHECK not set')
        """
        self._test_contract(parse_def=parse_def)

    @patch("scrapy.commands.check.ContractsManager")
    def test_run_with_opts_list_prints_spider(self, cm_cls_mock):
        output = StringIO()
        sys.stdout = output
        cmd = Command()
        cmd.settings = Mock(getwithbase=Mock(return_value={}))
        cm_cls_mock.return_value = cm_mock = Mock()
        spider_loader_mock = Mock()
        cmd.crawler_process = Mock(spider_loader=spider_loader_mock)
        spider_name = "FakeSpider"
        spider_cls_mock = Mock()
        type(spider_cls_mock).name = PropertyMock(return_value=spider_name)
        spider_loader_mock.load.side_effect = lambda x: {spider_name: spider_cls_mock}[
            x
        ]
        tested_methods = ["fakeMethod1", "fakeMethod2"]
        cm_mock.tested_methods_from_spidercls.side_effect = lambda x: {
            spider_cls_mock: tested_methods
        }[x]

        cmd.run([spider_name], Mock(list=True))

        self.assertEqual(
            "FakeSpider\n  * fakeMethod1\n  * fakeMethod2\n", output.getvalue()
        )
        sys.stdout = sys.__stdout__

    @patch("scrapy.commands.check.ContractsManager")
    def test_run_without_opts_list_does_not_crawl_spider_with_no_tested_methods(
        self, cm_cls_mock
    ):
        cmd = Command()
        cmd.settings = Mock(getwithbase=Mock(return_value={}))
        cm_cls_mock.return_value = cm_mock = Mock()
        spider_loader_mock = Mock()
        cmd.crawler_process = Mock(spider_loader=spider_loader_mock)
        spider_name = "FakeSpider"
        spider_cls_mock = Mock()
        spider_loader_mock.load.side_effect = lambda x: {spider_name: spider_cls_mock}[
            x
        ]
        tested_methods = []
        cm_mock.tested_methods_from_spidercls.side_effect = lambda x: {
            spider_cls_mock: tested_methods
        }[x]

        cmd.run([spider_name], Mock(list=False))

        cmd.crawler_process.crawl.assert_not_called()
