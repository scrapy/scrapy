"""Unit tests for scrapy.extensions.memusage.MemoryUsage"""

import sys
from unittest import TestCase
from unittest.mock import Mock, patch, MagicMock

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.settings import Settings
from scrapy.utils.test import get_crawler


class MemoryUsageTestCase(TestCase):
    """Tests for the MemoryUsage extension"""

    def _get_crawler(self, settings_dict=None):
        """Helper to get a test crawler"""
        settings = Settings()
        settings.setmodule('scrapy.settings.default_settings')
        if settings_dict:
            settings.update(settings_dict)
        return get_crawler(settings_obj=settings)

    def test_not_configured_when_disabled(self):
        """Test that NotConfigured is raised when MEMUSAGE_ENABLED is False"""
        crawler = self._get_crawler({
            'MEMUSAGE_ENABLED': False,
        })
        self.assertRaises(NotConfigured, MemoryUsage, crawler)

    @patch('scrapy.extensions.memusage.import_module')
    def test_not_configured_when_resource_unavailable(self, mock_import):
        """Test that NotConfigured is raised when resource module is unavailable"""
        mock_import.side_effect = ImportError()
        crawler = self._get_crawler({
            'MEMUSAGE_ENABLED': True,
        })
        self.assertRaises(NotConfigured, MemoryUsage, crawler)

    @patch('scrapy.extensions.memusage.import_module')
    def test_init_with_defaults(self, mock_import):
        """Test MemoryUsage initialization with default settings"""
        mock_resource = Mock()
        mock_import.return_value = mock_resource
        
        crawler = self._get_crawler({
            'MEMUSAGE_ENABLED': True,
            'MEMUSAGE_NOTIFY_MAIL': [],
            'MEMUSAGE_LIMIT_MB': 0,
            'MEMUSAGE_WARNING_MB': 0,
            'MEMUSAGE_CHECK_INTERVAL_SECONDS': 119.0,
        })
        
        mem_usage = MemoryUsage(crawler)
        self.assertEqual(mem_usage.limit, 0)
        self.assertEqual(mem_usage.warning, 0)
        self.assertFalse(mem_usage.warned)
        self.assertEqual(mem_usage.check_interval, 119.0)

    @patch('scrapy.extensions.memusage.import_module')
    def test_get_virtual_size(self, mock_import):
        """Test get_virtual_size returns correct value"""
        mock_resource = Mock()
        mock_rusage = Mock(ru_maxrss=1024)
        mock_resource.getrusage.return_value = mock_rusage
        mock_resource.RUSAGE_SELF = 0
        mock_import.return_value = mock_resource
        
        crawler = self._get_crawler({
            'MEMUSAGE_ENABLED': True,
        })
        
        mem_usage = MemoryUsage(crawler)
        
        with patch('sys.platform', 'linux'):
            # On Linux, ru_maxrss is in KB, so multiply by 1024
            size = mem_usage.get_virtual_size()
            self.assertEqual(size, 1024 * 1024)

    @patch('scrapy.extensions.memusage.import_module')
    def test_get_virtual_size_darwin(self, mock_import):
        """Test get_virtual_size on macOS"""
        mock_resource = Mock()
        mock_rusage = Mock(ru_maxrss=1024 * 1024)  # On macOS, already in bytes
        mock_resource.getrusage.return_value = mock_rusage
        mock_resource.RUSAGE_SELF = 0
        mock_import.return_value = mock_resource
        
        crawler = self._get_crawler({
            'MEMUSAGE_ENABLED': True,
        })
        
        mem_usage = MemoryUsage(crawler)
        
        with patch('sys.platform', 'darwin'):
            # On macOS, ru_maxrss is in bytes
            size = mem_usage.get_virtual_size()
            self.assertEqual(size, 1024 * 1024)

    @patch('scrapy.extensions.memusage.import_module')
    def test_from_crawler_classmethod(self, mock_import):
        """Test from_crawler classmethod"""
        mock_resource = Mock()
        mock_import.return_value = mock_resource
        
        crawler = self._get_crawler({
            'MEMUSAGE_ENABLED': True,
        })
        
        mem_usage = MemoryUsage.from_crawler(crawler)
        self.assertIsInstance(mem_usage, MemoryUsage)
        self.assertIs(mem_usage.crawler, crawler)
