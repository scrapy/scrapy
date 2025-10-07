import pytest
from unittest.mock import MagicMock, patch

from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage

class TestMemoryUsage:
    def setup_method(self):
        # Setup a mock crawler with all the dependencies necessary for MemoryUsage initialization
        self.crawler = MagicMock()
        self.crawler.settings.getbool.return_value = True
        self.crawler.settings.getlist.return_value = ["test@example.com"]
        self.crawler.settings.getint.side_effect = lambda key: {
            "MEMUSAGE_LIMIT_MB": 10,
            "MEMUSAGE_WARNING_MB": 5
        }[key]
        self.crawler.settings.getfloat.return_value = 1.0
        self.crawler.stats = MagicMock()
        self.crawler.engine = MagicMock()
        self.extension = MemoryUsage(self.crawler)

    def test_not_configured_when_disabled(self):
        # Test that NotConfigured is raised when MEMUSAGE_ENABLED is False
        self.crawler.settings.getbool.return_value = False
        with pytest.raises(NotConfigured):
            MemoryUsage(self.crawler)

    @patch("scrapy.extensions.memusage.import_module", side_effect=ImportError)
    def test_not_configured_when_no_resource_module(self, mock_import):
        # Test that NotConfigured is raised when the resource module cannot be imported
        with pytest.raises(NotConfigured):
            MemoryUsage(self.crawler)

    @patch.object(MemoryUsage, 'get_virtual_size', return_value=1024)
    def test_engine_started_sets_startup_stat_and_starts_tasks(self, mock_get_virtual_size):
        # Test that engine_started sets the startup memory usage stat and starts tasks
        self.extension.engine_started()
        self.crawler.stats.set_value.assert_called_with("memusage/startup", 1024)
        assert hasattr(self.extension, 'tasks')
        assert len(self.extension.tasks) > 0

    def test_engine_stopped_stops_tasks_and_only_stops_running_tasks(self):
        # Test that engine_stopped stops all running tasks and does not stop non-running tasks
        task1 = MagicMock(running=True)
        task2 = MagicMock(running=False)
        task3 = MagicMock(running=True)
        self.extension.tasks = [task1, task2, task3]
        self.extension.engine_stopped()
        task1.stop.assert_called_once()
        task2.stop.assert_not_called()
        task3.stop.assert_called_once()

    @patch.object(MemoryUsage, 'get_virtual_size', return_value=1024 * 5)
    def test_update_updates_max_memory_stat(self, mock_get_virtual_size):
        # Test that update updates the max memory usage stat
        self.extension.update()
        self.crawler.stats.max_value.assert_called_with("memusage/max", 1024 * 5)

    @patch.object(MemoryUsage, 'get_virtual_size', return_value=1024 * 1024 * 6)
    def test_check_warning_triggers_once(self, mock_get_virtual_size):
        # Test that check_warning triggers when memory usage exceeds the warning limit
        self.extension.warning = 1024 * 1024 * 5
        self.extension.warned = False
        self.extension.notify_mails = ["test@example.com"]

        self.extension._check_warning()
        self.crawler.stats.set_value.assert_called_with("memusage/warning_reached", 1)

        # Test that it doesn't trigger again if already warned
        self.crawler.stats.reset_mock()
        self.extension._check_warning()
        self.crawler.stats.set_value.assert_not_called()

    @patch.object(MemoryUsage, 'get_virtual_size', return_value=1024 * 1024 * 11)
    def test_check_limit_triggers_and_stops_engine(self, mock_get_virtual_size):
        # Test that check_limit triggers when memory usage exceeds the limit and stops the engine
        self.extension.limit = 1024 * 1024 * 10
        self.extension.notify_mails = ["test@example.com"]
        self.extension._send_report = MagicMock()

        self.extension._check_limit()
        self.crawler.stats.set_value.assert_called_with("memusage/limit_reached", 1)
        self.extension._send_report.assert_called_once()
        self.crawler.engine.close.assert_called_once()
