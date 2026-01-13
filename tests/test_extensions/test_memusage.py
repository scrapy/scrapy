import unittest
from unittest.mock import MagicMock, patch
from scrapy.extensions.memusage import MemoryUsage
from scrapy.crawler import Crawler
from scrapy.spiders import Spider
import sys
from scrapy.settings import Settings

@unittest.skipIf(sys.platform.startswith("win"), "MemoryUsage extension not available on Windows")
class MemoryUsageTestCase(unittest.TestCase):

    @patch.object(MemoryUsage, "_send_report")
    @patch("scrapy.extensions.memusage.get_engine_status", return_value={})
    @patch("scrapy.extensions.memusage._schedule_coro")
    @patch("scrapy.extensions.memusage.create_looping_call")
    @patch.object(MemoryUsage, "get_virtual_size")

    def test_memusage_under_limit(
        self,
        mock_get_virtual_size,
        mock_create_loop,
        mock_schedule,
        mock_engine_status,
        mock_send_report,
    ):
        MB = 1024 * 1024
        mock_get_virtual_size.return_value = 50 * MB

        mock_task = MagicMock()
        mock_task.running = True
        mock_create_loop.return_value = mock_task

        settings = Settings({
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 100,
            "MEMUSAGE_WARNING_MB": 80,
        })

        crawler = Crawler(Spider, settings)
        crawler.stats = MagicMock()
        crawler.engine = MagicMock()
        crawler.engine.spider = None
        crawler.stop_async = MagicMock()

        mem_usage = MemoryUsage.from_crawler(crawler)
        mem_usage.engine_started()

        mem_usage.update()
        mem_usage._check_warning()
        mem_usage._check_limit()

        self.assertFalse(mem_usage.warned)
        self.assertLess(mem_usage.get_virtual_size(), mem_usage.limit * 1024 * 1024)
        crawler.stats.max_value.assert_any_call("memusage/max", 50 * MB)
        crawler.engine.close_spider_async.assert_not_called()
        crawler.stop_async.assert_not_called()


    @patch.object(MemoryUsage, "_send_report")
    @patch("scrapy.extensions.memusage.get_engine_status", return_value={})
    @patch("scrapy.extensions.memusage._schedule_coro")
    @patch("scrapy.extensions.memusage.create_looping_call")
    @patch("scrapy.extensions.memusage.MailSender")
    @patch.object(MemoryUsage, "get_virtual_size")
    def test_memusage_warning_triggered(
        self,
        mock_get_virtual_size,
        mock_mail_sender,
        mock_engine_status,
        mock_schedule,
        mock_create_loop,
        mock_send_report,
    ):

        MB = 1024 * 1024
        mock_get_virtual_size.return_value = 90 * MB

        mock_task = MagicMock()
        mock_task.running = True
        mock_create_loop.return_value = mock_task

        mock_mail_instance = MagicMock()
        mock_mail_sender.from_crawler.return_value = mock_mail_instance

        settings = Settings({
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 100,
            "MEMUSAGE_WARNING_MB": 80,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 10,
            "MEMUSAGE_NOTIFY_MAIL": ["test@example.com"],
        })

        crawler = Crawler(Spider, settings)
        crawler.stats = MagicMock()
        crawler.engine = MagicMock()
        crawler.engine.spider = None
        crawler.stop_async = MagicMock()

        mem_usage = MemoryUsage.from_crawler(crawler)
        mem_usage.engine_started()

        mem_usage.update()
        mem_usage._check_warning()
        mem_usage._check_limit()

        self.assertTrue(mem_usage.warned)
        self.assertGreater(mem_usage.get_virtual_size(), mem_usage.limit * 1024 * 1024)
        crawler.stats.set_value.assert_any_call("memusage/warning_reached", 1)
        mock_mail_instance.send.assert_called_once()
        crawler.engine.close_spider_async.assert_not_called()
        crawler.stop_async.assert_not_called()


    @patch.object(MemoryUsage, "_send_report")
    @patch("scrapy.extensions.memusage.get_engine_status", return_value={})
    @patch("scrapy.extensions.memusage._schedule_coro")
    @patch("scrapy.extensions.memusage.create_looping_call")
    @patch.object(MemoryUsage, "get_virtual_size")
    def test_memusage_limit_exceeded(
        self,
        mock_get_virtual_size,
        mock_create_loop,
        mock_schedule,
        mock_engine_status,
        mock_send_report,
    ):
        MB = 1024 * 1024
        mock_get_virtual_size.return_value = 120 * MB

        mock_task = MagicMock()
        mock_task.running = True
        mock_create_loop.return_value = mock_task

        settings = Settings({
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 100,
            "MEMUSAGE_WARNING_MB": 80,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 10,
        })

        crawler = Crawler(Spider, settings)
        crawler.stats = MagicMock()
        crawler.engine = MagicMock()
        crawler.engine.spider = Spider(name="testspider")
        crawler.engine.close_spider_async = MagicMock()
        crawler.stop_async = MagicMock()

        mem_usage = MemoryUsage.from_crawler(crawler)
        mem_usage.engine_started()

        mem_usage.update()
        mem_usage._check_warning()
        mem_usage._check_limit()

        self.assertGreater(mem_usage.get_virtual_size(), mem_usage.limit * 1024 * 1024)
        crawler.stats.set_value.assert_any_call("memusage/limit_reached", 1)
        crawler.engine.close_spider_async.assert_called_once_with(
            reason="memusage_exceeded"
        )
        crawler.stop_async.assert_not_called()


if __name__ == "__main__":
    unittest.main()