from unittest.mock import Mock, patch

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler


UNSET = object()


def get_memusage_crawler(settings=None):
    """Helper to create a crawler with MEMUSAGE_ENABLED=True"""
    settings = settings or {}
    settings["MEMUSAGE_ENABLED"] = True
    return get_crawler(settings_dict=settings)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (UNSET, False),
        (False, False),
        (True, True),
    ],
)
def test_enabled(value, expected):
    """Test that MemoryUsage is only enabled when MEMUSAGE_ENABLED is True"""
    settings = {}
    if value is not UNSET:
        settings["MEMUSAGE_ENABLED"] = value
    crawler = get_crawler(settings_dict=settings)
    
    # Mock the resource module to avoid ImportError on Windows
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_import.return_value = Mock()
        
        if expected:
            ext = build_from_crawler(MemoryUsage, crawler)
            assert isinstance(ext, MemoryUsage)
        else:
            with pytest.raises(NotConfigured):
                build_from_crawler(MemoryUsage, crawler)


def test_resource_not_available():
    """Test that MemoryUsage raises NotConfigured when resource module is unavailable"""
    settings = {"MEMUSAGE_ENABLED": True}
    crawler = get_crawler(settings_dict=settings)
    
    # Simulate ImportError for resource module
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_import.side_effect = ImportError("No module named 'resource'")
        
        with pytest.raises(NotConfigured):
            build_from_crawler(MemoryUsage, crawler)


def test_get_virtual_size_darwin():
    """Test get_virtual_size on macOS (darwin) - returns bytes directly"""
    crawler = get_memusage_crawler()
    
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_resource = Mock()
        mock_resource.RUSAGE_SELF = 0
        mock_rusage = Mock()
        mock_rusage.ru_maxrss = 1024 * 1024  # 1 MB in bytes
        mock_resource.getrusage.return_value = mock_rusage
        mock_import.return_value = mock_resource
        
        ext = build_from_crawler(MemoryUsage, crawler)
        
        with patch("sys.platform", "darwin"):
            size = ext.get_virtual_size()
            # On macOS, ru_maxrss is already in bytes
            assert size == 1024 * 1024


def test_get_virtual_size_linux():
    """Test get_virtual_size on Linux - converts KB to bytes"""
    crawler = get_memusage_crawler()
    
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_resource = Mock()
        mock_resource.RUSAGE_SELF = 0
        mock_rusage = Mock()
        mock_rusage.ru_maxrss = 1024  # 1 MB in KB
        mock_resource.getrusage.return_value = mock_rusage
        mock_import.return_value = mock_resource
        
        ext = build_from_crawler(MemoryUsage, crawler)
        
        with patch("sys.platform", "linux"):
            size = ext.get_virtual_size()
            # On Linux, ru_maxrss is in KB, so multiply by 1024
            assert size == 1024 * 1024


def test_engine_started_sets_startup_stat():
    """Test that engine_started sets the memusage/startup stat"""
    crawler = get_memusage_crawler()
    
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_resource = Mock()
        mock_import.return_value = mock_resource
        
        ext = build_from_crawler(MemoryUsage, crawler)
        ext.get_virtual_size = Mock(return_value=10 * 1024 * 1024)  # 10 MB
        
        # Mock create_looping_call to avoid actual task scheduling
        with patch("scrapy.extensions.memusage.create_looping_call") as mock_create:
            mock_task = Mock()
            mock_create.return_value = mock_task
            
            ext.engine_started()
            
            # Check that startup stat was set
            assert crawler.stats.get_value("memusage/startup") == 10 * 1024 * 1024
            # Check that tasks were created
            assert len(ext.tasks) > 0


def test_update_sets_max_stat():
    """Test that update() sets the memusage/max stat"""
    crawler = get_memusage_crawler()
    
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_resource = Mock()
        mock_import.return_value = mock_resource
        
        ext = build_from_crawler(MemoryUsage, crawler)
        ext.get_virtual_size = Mock(return_value=20 * 1024 * 1024)  # 20 MB
        
        ext.update()
        
        # Check that max stat was set
        assert crawler.stats.get_value("memusage/max") == 20 * 1024 * 1024


def test_check_limit_not_exceeded():
    """Test _check_limit when memory limit is not exceeded"""
    settings = {"MEMUSAGE_LIMIT_MB": 100}
    crawler = get_memusage_crawler(settings)
    
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_resource = Mock()
        mock_import.return_value = mock_resource
        
        ext = build_from_crawler(MemoryUsage, crawler)
        ext.get_virtual_size = Mock(return_value=50 * 1024 * 1024)  # 50 MB
        
        # Mock engine
        crawler.engine = Mock()
        
        ext._check_limit()
        
        # Should not set limit_reached stat
        assert crawler.stats.get_value("memusage/limit_reached") is None


def test_check_limit_exceeded():
    """Test _check_limit when memory limit is exceeded"""
    settings = {"MEMUSAGE_LIMIT_MB": 50}
    crawler = get_memusage_crawler(settings)
    
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_resource = Mock()
        mock_import.return_value = mock_resource
        
        ext = build_from_crawler(MemoryUsage, crawler)
        ext.get_virtual_size = Mock(return_value=100 * 1024 * 1024)  # 100 MB
        
        # Mock engine and spider
        crawler.engine = Mock()
        crawler.engine.spider = Mock()
        
        with patch("scrapy.extensions.memusage._schedule_coro") as mock_schedule:
            ext._check_limit()
            
            # Should set limit_reached stat
            assert crawler.stats.get_value("memusage/limit_reached") == 1
            # Should schedule spider close
            assert mock_schedule.called


def test_check_limit_exceeded_with_notification():
    """Test _check_limit sends email when limit is exceeded and notify_mails is set"""
    settings = {
        "MEMUSAGE_LIMIT_MB": 50,
        "MEMUSAGE_NOTIFY_MAIL": ["admin@example.com"],
        "BOT_NAME": "testbot",
    }
    crawler = get_memusage_crawler(settings)
    
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_resource = Mock()
        mock_import.return_value = mock_resource
        
        ext = build_from_crawler(MemoryUsage, crawler)
        ext.get_virtual_size = Mock(return_value=100 * 1024 * 1024)  # 100 MB
        ext._send_report = Mock()
        
        # Mock engine and spider
        crawler.engine = Mock()
        crawler.engine.spider = Mock()
        
        with patch("scrapy.extensions.memusage._schedule_coro"):
            ext._check_limit()
            
            # Should call _send_report
            assert ext._send_report.called
            # Should set limit_notified stat
            assert crawler.stats.get_value("memusage/limit_notified") == 1


def test_check_warning_first_time():
    """Test _check_warning when warning threshold is exceeded for the first time"""
    settings = {"MEMUSAGE_WARNING_MB": 50}
    crawler = get_memusage_crawler(settings)
    
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_resource = Mock()
        mock_import.return_value = mock_resource
        
        ext = build_from_crawler(MemoryUsage, crawler)
        ext.get_virtual_size = Mock(return_value=100 * 1024 * 1024)  # 100 MB
        
        assert ext.warned is False
        
        ext._check_warning()
        
        # Should set warning_reached stat
        assert crawler.stats.get_value("memusage/warning_reached") == 1
        # Should set warned flag
        assert ext.warned is True


def test_check_warning_already_warned():
    """Test _check_warning doesn't warn again after first warning"""
    settings = {"MEMUSAGE_WARNING_MB": 50}
    crawler = get_memusage_crawler(settings)
    
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_resource = Mock()
        mock_import.return_value = mock_resource
        
        ext = build_from_crawler(MemoryUsage, crawler)
        ext.get_virtual_size = Mock(return_value=100 * 1024 * 1024)  # 100 MB
        ext.warned = True  # Already warned
        
        ext._check_warning()
        
        # Should not set warning_reached stat again
        assert crawler.stats.get_value("memusage/warning_reached") is None


def test_check_warning_not_exceeded():
    """Test _check_warning when warning threshold is not exceeded"""
    settings = {"MEMUSAGE_WARNING_MB": 100}
    crawler = get_memusage_crawler(settings)
    
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_resource = Mock()
        mock_import.return_value = mock_resource
        
        ext = build_from_crawler(MemoryUsage, crawler)
        ext.get_virtual_size = Mock(return_value=50 * 1024 * 1024)  # 50 MB
        
        ext._check_warning()
        
        # Should not set warning_reached stat
        assert crawler.stats.get_value("memusage/warning_reached") is None
        # Should not set warned flag
        assert ext.warned is False


def test_check_warning_with_notification():
    """Test _check_warning sends email when threshold is exceeded and notify_mails is set"""
    settings = {
        "MEMUSAGE_WARNING_MB": 50,
        "MEMUSAGE_NOTIFY_MAIL": ["admin@example.com"],
        "BOT_NAME": "testbot",
    }
    crawler = get_memusage_crawler(settings)
    
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_resource = Mock()
        mock_import.return_value = mock_resource
        
        ext = build_from_crawler(MemoryUsage, crawler)
        ext.get_virtual_size = Mock(return_value=100 * 1024 * 1024)  # 100 MB
        ext._send_report = Mock()
        
        ext._check_warning()
        
        # Should call _send_report
        assert ext._send_report.called
        # Should set warning_notified stat
        assert crawler.stats.get_value("memusage/warning_notified") == 1


def test_engine_stopped_stops_tasks():
    """Test that engine_stopped stops all running tasks"""
    crawler = get_memusage_crawler()
    
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_resource = Mock()
        mock_import.return_value = mock_resource
        
        ext = build_from_crawler(MemoryUsage, crawler)
        
        # Create mock tasks
        task1 = Mock()
        task1.running = True
        task2 = Mock()
        task2.running = False
        task3 = Mock()
        task3.running = True
        
        ext.tasks = [task1, task2, task3]
        
        ext.engine_stopped()
        
        # Should stop running tasks
        assert task1.stop.called
        assert not task2.stop.called  # Not running, shouldn't be stopped
        assert task3.stop.called


def test_send_report():
    """Test _send_report sends email with correct information"""
    settings = {"BOT_NAME": "testbot"}
    crawler = get_memusage_crawler(settings)
    
    with patch("scrapy.extensions.memusage.import_module") as mock_import:
        mock_resource = Mock()
        mock_import.return_value = mock_resource
        
        ext = build_from_crawler(MemoryUsage, crawler)
        ext.get_virtual_size = Mock(return_value=100 * 1024 * 1024)  # 100 MB
        ext.mail = Mock()
        
        # Set up stats
        crawler.stats.set_value("memusage/startup", 50 * 1024 * 1024)
        crawler.stats.set_value("memusage/max", 150 * 1024 * 1024)
        
        # Mock engine
        crawler.engine = Mock()
        
        with patch("scrapy.extensions.memusage.get_engine_status") as mock_status:
            mock_status.return_value = {"test": "status"}
            
            ext._send_report(["admin@example.com"], "Test Subject")
            
            # Should call mail.send
            assert ext.mail.send.called
            call_args = ext.mail.send.call_args[0]
            assert call_args[0] == ["admin@example.com"]
            assert call_args[1] == "Test Subject"
            # Check that message contains memory info
            message = call_args[2]
            assert "50" in message  # startup memory
            assert "150" in message  # max memory
            assert "100" in message  # current memory
