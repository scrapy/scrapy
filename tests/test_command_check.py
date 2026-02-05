from __future__ import annotations

import sys
from io import StringIO
from typing import TYPE_CHECKING
from unittest import TestCase
from unittest.mock import Mock, PropertyMock, call, patch

from scrapy.commands.check import Command, TextTestResult
from tests.test_commands import TestProjectBase
from tests.utils.cmdline import proc

if TYPE_CHECKING:
    from pathlib import Path


class DummyTestCase(TestCase):
    pass


class TestCheckCommand(TestProjectBase):
    spider_name = "check_spider"

    def _write_contract(self, proj_path: Path, contracts: str, parse_def: str) -> None:
        spider = proj_path / self.project_name / "spiders" / "checkspider.py"
        spider.write_text(
            f"""
import scrapy

class CheckSpider(scrapy.Spider):
    name = '{self.spider_name}'
    start_urls = ['data:,']

    custom_settings = {{
        "DOWNLOAD_DELAY": 0,
    }}

    def parse(self, response, **cb_kwargs):
        \"\"\"
        @url data:,
        {contracts}
        \"\"\"
        {parse_def}
        """,
            encoding="utf-8",
        )

    def _test_contract(
        self, proj_path: Path, contracts: str = "", parse_def: str = "pass"
    ) -> None:
        self._write_contract(proj_path, contracts, parse_def)
        ret, out, err = proc("check", cwd=proj_path)
        assert "F" not in out
        assert "OK" in err
        assert ret == 0

    def test_check_returns_requests_contract(self, proj_path: Path) -> None:
        contracts = """
        @returns requests 1
        """
        parse_def = """
        yield scrapy.Request(url='http://next-url.com')
        """
        self._test_contract(proj_path, contracts, parse_def)

    def test_check_returns_items_contract(self, proj_path: Path) -> None:
        contracts = """
        @returns items 1
        """
        parse_def = """
        yield {'key1': 'val1', 'key2': 'val2'}
        """
        self._test_contract(proj_path, contracts, parse_def)

    def test_check_cb_kwargs_contract(self, proj_path: Path) -> None:
        contracts = """
        @cb_kwargs {"arg1": "val1", "arg2": "val2"}
        """
        parse_def = """
        if len(cb_kwargs.items()) == 0:
            raise Exception("Callback args not set")
        """
        self._test_contract(proj_path, contracts, parse_def)

    def test_check_scrapes_contract(self, proj_path: Path) -> None:
        contracts = """
        @scrapes key1 key2
        """
        parse_def = """
        yield {'key1': 'val1', 'key2': 'val2'}
        """
        self._test_contract(proj_path, contracts, parse_def)

    def test_check_all_default_contracts(self, proj_path: Path) -> None:
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
        self._test_contract(proj_path, contracts, parse_def)

    def test_SCRAPY_CHECK_set(self, proj_path: Path) -> None:
        parse_def = """
        import os
        if not os.environ.get('SCRAPY_CHECK'):
            raise Exception('SCRAPY_CHECK not set')
        """
        self._test_contract(proj_path, parse_def=parse_def)

    def test_printSummary_with_unsuccessful_test_result_without_errors_and_without_failures(
        self,
    ) -> None:
        result = TextTestResult(Mock(), descriptions=False, verbosity=1)
        start_time = 1.0
        stop_time = 2.0
        result.testsRun = 5
        result.failures = []
        result.errors = []
        result.unexpectedSuccesses = [DummyTestCase(), DummyTestCase()]
        with patch.object(result.stream, "write") as mock_write:
            result.printSummary(start_time, stop_time)
            mock_write.assert_has_calls([call("FAILED"), call("\n")])

    def test_printSummary_with_unsuccessful_test_result_with_only_failures(
        self,
    ) -> None:
        result = TextTestResult(Mock(), descriptions=False, verbosity=1)
        start_time = 1.0
        stop_time = 2.0
        result.testsRun = 5
        result.failures = [(DummyTestCase(), "failure")]
        result.errors = []
        with patch.object(result.stream, "writeln") as mock_write:
            result.printSummary(start_time, stop_time)
            mock_write.assert_called_with(" (failures=1)")

    def test_printSummary_with_unsuccessful_test_result_with_only_errors(self) -> None:
        result = TextTestResult(Mock(), descriptions=False, verbosity=1)
        start_time = 1.0
        stop_time = 2.0
        result.testsRun = 5
        result.failures = []
        result.errors = [(DummyTestCase(), "error")]
        with patch.object(result.stream, "writeln") as mock_write:
            result.printSummary(start_time, stop_time)
            mock_write.assert_called_with(" (errors=1)")

    def test_printSummary_with_unsuccessful_test_result_with_both_failures_and_errors(
        self,
    ) -> None:
        result = TextTestResult(Mock(), descriptions=False, verbosity=1)
        start_time = 1.0
        stop_time = 2.0
        result.testsRun = 5
        result.failures = [(DummyTestCase(), "failure")]
        result.errors = [(DummyTestCase(), "error")]
        with patch.object(result.stream, "writeln") as mock_write:
            result.printSummary(start_time, stop_time)
            mock_write.assert_called_with(" (failures=1, errors=1)")

    @patch("scrapy.commands.check.ContractsManager")
    def test_run_with_opts_list_prints_spider(self, cm_cls_mock) -> None:
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

        assert output.getvalue() == "FakeSpider\n  * fakeMethod1\n  * fakeMethod2\n"
        sys.stdout = sys.__stdout__

    @patch("scrapy.commands.check.ContractsManager")
    def test_run_without_opts_list_does_not_crawl_spider_with_no_tested_methods(
        self, cm_cls_mock
    ) -> None:
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
        tested_methods: list[str] = []
        cm_mock.tested_methods_from_spidercls.side_effect = lambda x: {
            spider_cls_mock: tested_methods
        }[x]

        cmd.run([spider_name], Mock(list=False))

        cmd.crawler_process.crawl.assert_not_called()
