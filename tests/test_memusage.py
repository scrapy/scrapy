import sys
from unittest.mock import Mock, patch

import pytest
from twisted.internet.defer import inlineCallbacks

from scrapy import Spider
from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.settings.default_settings import (
    MEMUSAGE_CHECK_INTERVAL_SECONDS,
    MEMUSAGE_ENABLED,
    MEMUSAGE_LIMIT_MB,
    MEMUSAGE_NOTIFY_MAIL,
    MEMUSAGE_WARNING_MB,
)
from scrapy.utils.test import get_crawler as _get_crawler

UNSET = object()


def get_crawler(settings=None, spidercls=None):
    """Helper function to get a crawler with MemoryUsage enabled."""
    settings = settings or {}
    if "MEMUSAGE_ENABLED" not in settings:
        settings["MEMUSAGE_ENABLED"] = True
    return _get_crawler(settings_dict=settings, spidercls=spidercls)


class TestMemoryUsage:
    """Test suite for the MemoryUsage extension."""

    @pytest.mark.parametrize(
        ("value", "should_raise"),
        [
            (True, False),
            (False, True),
        ],
    )
    def test_memusage_enabled(self, value, should_raise):
        """Test that MemoryUsage extension is only enabled when MEMUSAGE_ENABLED is True."""
        settings = {"MEMUSAGE_ENABLED": value}

        crawler = _get_crawler(settings_dict=settings)
        if should_raise:
            with pytest.raises(NotConfigured):
                MemoryUsage.from_crawler(crawler)
        else:
            ext = MemoryUsage.from_crawler(crawler)
            assert isinstance(ext, MemoryUsage)

    def test_memusage_default_enabled(self):
        """Test that MemoryUsage extension is enabled by default."""
        settings = {}  # Use default MEMUSAGE_ENABLED = True
        crawler = _get_crawler(settings_dict=settings)
        ext = MemoryUsage.from_crawler(crawler)
        assert isinstance(ext, MemoryUsage)

    def test_resource_module_not_available(self):
        """Test that NotConfigured is raised when resource module is not available."""
        with patch("scrapy.extensions.memusage.import_module") as mock_import:
            mock_import.side_effect = ImportError("No module named 'resource'")
            crawler = get_crawler()
            with pytest.raises(NotConfigured):
                MemoryUsage.from_crawler(crawler)

    def test_init_default_settings(self):
        """Test initialization with default settings."""
        crawler = get_crawler()
        ext = MemoryUsage.from_crawler(crawler)
        
        assert ext.crawler is crawler
        assert ext.warned is False
        assert ext.notify_mails == MEMUSAGE_NOTIFY_MAIL
        assert ext.limit == MEMUSAGE_LIMIT_MB * 1024 * 1024
        assert ext.warning == MEMUSAGE_WARNING_MB * 1024 * 1024
        assert ext.check_interval == MEMUSAGE_CHECK_INTERVAL_SECONDS

    def test_init_custom_settings(self):
        """Test initialization with custom settings."""
        settings = {
            "MEMUSAGE_NOTIFY_MAIL": ["admin@example.com", "dev@example.com"],
            "MEMUSAGE_LIMIT_MB": 512,
            "MEMUSAGE_WARNING_MB": 256,
            "MEMUSAGE_CHECK_INTERVAL_SECONDS": 30.0,
        }
        crawler = get_crawler(settings)
        ext = MemoryUsage.from_crawler(crawler)
        
        assert ext.notify_mails == ["admin@example.com", "dev@example.com"]
        assert ext.limit == 512 * 1024 * 1024
        assert ext.warning == 256 * 1024 * 1024
        assert ext.check_interval == 30.0

    def test_get_virtual_size_macos(self):
        """Test get_virtual_size on macOS (ru_maxrss in bytes)."""
        crawler = get_crawler()
        ext = MemoryUsage.from_crawler(crawler)
        
        mock_usage = Mock()
        mock_usage.ru_maxrss = 1024 * 1024  # 1MB in bytes
        
        with patch.object(ext.resource, "getrusage", return_value=mock_usage):
            with patch.object(sys, "platform", "darwin"):
                size = ext.get_virtual_size()
                assert size == 1024 * 1024  # Should return bytes directly

    def test_get_virtual_size_linux(self):
        """Test get_virtual_size on Linux (ru_maxrss in KB)."""
        crawler = get_crawler()
        ext = MemoryUsage.from_crawler(crawler)
        
        mock_usage = Mock()
        mock_usage.ru_maxrss = 1024  # 1MB in KB
        
        with patch.object(ext.resource, "getrusage", return_value=mock_usage):
            with patch.object(sys, "platform", "linux"):
                size = ext.get_virtual_size()
                assert size == 1024 * 1024  # Should convert KB to bytes

    @inlineCallbacks
    def test_engine_started_no_limits(self):
        """Test engine_started signal handler when no limits are set."""
        crawler = get_crawler({"MEMUSAGE_LIMIT_MB": 0, "MEMUSAGE_WARNING_MB": 0})
        ext = MemoryUsage.from_crawler(crawler)
        
        with patch.object(ext, "get_virtual_size", return_value=100 * 1024 * 1024):
            with patch("scrapy.extensions.memusage.create_looping_call") as mock_create:
                mock_task = Mock()
                mock_create.return_value = mock_task
                
                yield ext.engine_started()
                
                # Should only create one task for update
                assert mock_create.call_count == 1
                mock_create.assert_called_with(ext.update)
                mock_task.start.assert_called_once_with(ext.check_interval, now=True)
                assert len(ext.tasks) == 1

    @inlineCallbacks
    def test_engine_started_with_limits(self):
        """Test engine_started signal handler when limits are set."""
        settings = {"MEMUSAGE_LIMIT_MB": 512, "MEMUSAGE_WARNING_MB": 256}
        crawler = get_crawler(settings)
        ext = MemoryUsage.from_crawler(crawler)
        
        with patch.object(ext, "get_virtual_size", return_value=100 * 1024 * 1024):
            with patch("scrapy.extensions.memusage.create_looping_call") as mock_create:
                mock_task = Mock()
                mock_create.return_value = mock_task
                
                yield ext.engine_started()
                
                # Should create three tasks: update, limit check, warning check
                assert mock_create.call_count == 3
                assert len(ext.tasks) == 3
                assert mock_task.start.call_count == 3

    def test_engine_stopped(self):
        """Test engine_stopped signal handler stops all running tasks."""
        crawler = get_crawler()
        ext = MemoryUsage.from_crawler(crawler)
        
        # Create mock tasks
        running_task = Mock()
        running_task.running = True
        stopped_task = Mock()
        stopped_task.running = False
        
        ext.tasks = [running_task, stopped_task]
        
        ext.engine_stopped()
        
        running_task.stop.assert_called_once()
        stopped_task.stop.assert_not_called()

    def test_update(self):
        """Test update method sets max memory usage stat."""
        crawler = get_crawler()
        ext = MemoryUsage.from_crawler(crawler)
        
        with patch.object(ext, "get_virtual_size", return_value=200 * 1024 * 1024):
            with patch.object(crawler.stats, "max_value") as mock_max_value:
                ext.update()
                
                mock_max_value.assert_called_once_with(
                    "memusage/max", 200 * 1024 * 1024
                )

    def test_check_limit_not_exceeded(self):
        """Test _check_limit when memory usage is within limits."""
        settings = {"MEMUSAGE_LIMIT_MB": 512}
        crawler = get_crawler(settings)
        ext = MemoryUsage.from_crawler(crawler)
        
        # Mock engine and stats
        crawler.engine = Mock()
        
        with patch.object(ext, "get_virtual_size", return_value=256 * 1024 * 1024):
            with patch.object(crawler.stats, "set_value") as mock_set_value:
                ext._check_limit()
                
                # Should not set limit_reached stat
                mock_set_value.assert_not_called()

    def test_check_limit_exceeded_with_spider(self):
        """Test _check_limit when memory usage exceeds limit with active spider."""
        settings = {"MEMUSAGE_LIMIT_MB": 256}
        crawler = get_crawler(settings)
        ext = MemoryUsage.from_crawler(crawler)
        
        # Mock engine and spider
        mock_spider = Mock()
        crawler.engine = Mock()
        crawler.engine.spider = mock_spider
        
        with patch.object(ext, "get_virtual_size", return_value=512 * 1024 * 1024):
            with patch("scrapy.extensions.memusage._schedule_coro") as mock_schedule:
                with patch.object(crawler.stats, "set_value") as mock_set_value:
                    ext._check_limit()
                    
                    # Should set limit_reached stat
                    mock_set_value.assert_called_with("memusage/limit_reached", 1)
                    # Should schedule spider close
                    mock_schedule.assert_called_once()

    def test_check_limit_exceeded_without_spider(self):
        """Test _check_limit when memory usage exceeds limit without active spider."""
        settings = {"MEMUSAGE_LIMIT_MB": 256}
        crawler = get_crawler(settings)
        ext = MemoryUsage.from_crawler(crawler)
        
        # Mock engine without spider
        crawler.engine = Mock()
        crawler.engine.spider = None
        
        with patch.object(ext, "get_virtual_size", return_value=512 * 1024 * 1024):
            with patch("scrapy.extensions.memusage._schedule_coro") as mock_schedule:
                ext._check_limit()
                
                # Should schedule crawler stop
                mock_schedule.assert_called_once()

    def test_check_limit_exceeded_with_notification(self):
        """Test _check_limit sends notification email when limit is exceeded."""
        settings = {
            "MEMUSAGE_LIMIT_MB": 256,
            "MEMUSAGE_NOTIFY_MAIL": ["admin@example.com"],
            "BOT_NAME": "test_bot",
        }
        crawler = get_crawler(settings)
        ext = MemoryUsage.from_crawler(crawler)
        
        # Mock engine
        crawler.engine = Mock()
        crawler.engine.spider = None
        
        with patch.object(ext, "get_virtual_size", return_value=512 * 1024 * 1024):
            with patch.object(ext, "_send_report") as mock_send:
                with patch("scrapy.extensions.memusage._schedule_coro"):
                    with patch("socket.gethostname", return_value="test-host"):
                        with patch.object(crawler.stats, "set_value") as mock_set_value:
                            ext._check_limit()
                            
                            mock_send.assert_called_once()
                            args = mock_send.call_args[0]
                            assert args[0] == ["admin@example.com"]
                            assert "test_bot terminated" in args[1]
                            assert "256.0MiB" in args[1]  # The implementation uses float formatting
                            assert "test-host" in args[1]
                            
                            mock_set_value.assert_any_call("memusage/limit_notified", 1)

    def test_check_warning_not_reached(self):
        """Test _check_warning when memory usage is below warning threshold."""
        settings = {"MEMUSAGE_WARNING_MB": 256}
        crawler = get_crawler(settings)
        ext = MemoryUsage.from_crawler(crawler)
        
        with patch.object(ext, "get_virtual_size", return_value=128 * 1024 * 1024):
            with patch.object(crawler.stats, "set_value") as mock_set_value:
                ext._check_warning()
                
                # Should not set warning_reached stat
                mock_set_value.assert_not_called()
                assert ext.warned is False

    def test_check_warning_reached(self):
        """Test _check_warning when memory usage reaches warning threshold."""
        settings = {"MEMUSAGE_WARNING_MB": 256}
        crawler = get_crawler(settings)
        ext = MemoryUsage.from_crawler(crawler)
        
        with patch.object(ext, "get_virtual_size", return_value=512 * 1024 * 1024):
            with patch.object(crawler.stats, "set_value") as mock_set_value:
                ext._check_warning()
                
                # Should set warning_reached stat
                mock_set_value.assert_called_with("memusage/warning_reached", 1)
                assert ext.warned is True

    def test_check_warning_only_once(self):
        """Test _check_warning only warns once even if called multiple times."""
        settings = {"MEMUSAGE_WARNING_MB": 256}
        crawler = get_crawler(settings)
        ext = MemoryUsage.from_crawler(crawler)
        
        with patch.object(ext, "get_virtual_size", return_value=512 * 1024 * 1024):
            with patch.object(crawler.stats, "set_value") as mock_set_value:
                # First call should warn
                ext._check_warning()
                assert ext.warned is True
                call_count = mock_set_value.call_count
                
                # Second call should not warn again
                ext._check_warning()
                assert mock_set_value.call_count == call_count

    def test_check_warning_with_notification(self):
        """Test _check_warning sends notification email when warning is reached."""
        settings = {
            "MEMUSAGE_WARNING_MB": 256,
            "MEMUSAGE_NOTIFY_MAIL": ["admin@example.com"],
            "BOT_NAME": "test_bot",
        }
        crawler = get_crawler(settings)
        ext = MemoryUsage.from_crawler(crawler)
        
        with patch.object(ext, "get_virtual_size", return_value=512 * 1024 * 1024):
            with patch.object(ext, "_send_report") as mock_send:
                with patch("socket.gethostname", return_value="test-host"):
                    with patch.object(crawler.stats, "set_value") as mock_set_value:
                        ext._check_warning()
                        
                        mock_send.assert_called_once()
                        args = mock_send.call_args[0]
                        assert args[0] == ["admin@example.com"]
                        assert "test_bot warning" in args[1]
                        assert "256.0MiB" in args[1]  # The implementation uses float formatting
                        assert "test-host" in args[1]
                        
                        mock_set_value.assert_any_call("memusage/warning_notified", 1)

    def test_send_report(self):
        """Test _send_report generates and sends email with memory usage info."""
        crawler = get_crawler()
        ext = MemoryUsage.from_crawler(crawler)
        
        # Mock engine and stats
        crawler.engine = Mock()
        
        def mock_get_value(key, default=None):
            values = {
                "memusage/startup": 50 * 1024 * 1024,
                "memusage/max": 200 * 1024 * 1024,
            }
            return values.get(key, default)
        
        with patch.object(crawler.stats, "get_value", side_effect=mock_get_value):
            with patch.object(ext, "get_virtual_size", return_value=180 * 1024 * 1024):
                with patch("scrapy.extensions.memusage.get_engine_status") as mock_status:
                    with patch.object(ext.mail, "send") as mock_mail_send:
                        mock_status.return_value = {"engine.state": "running"}
                        
                        ext._send_report(["test@example.com"], "Test Subject")
                        
                        # Verify mail was sent
                        mock_mail_send.assert_called_once()
                        args = mock_mail_send.call_args[0]
                        assert args[0] == ["test@example.com"]
                        assert args[1] == "Test Subject"
                        
                        # Verify email body contains memory usage info
                        body = args[2]
                        assert "50.0M" in body  # startup memory (with float format)
                        assert "200.0M" in body  # max memory (with float format)
                        assert "180.0M" in body  # current memory (with float format)
                        assert "ENGINE STATUS" in body

    def test_from_crawler_class_method(self):
        """Test that from_crawler class method returns instance of MemoryUsage."""
        crawler = get_crawler()
        ext = MemoryUsage.from_crawler(crawler)
        assert isinstance(ext, MemoryUsage)
        assert ext.crawler is crawler
