import os
from tests import mock
import unittest

from scrapy.exceptions import NotConfigured
from scrapy.utils.project import get_project_path, inside_project


class UtilsProjectTestCase(unittest.TestCase):

    @mock.patch('scrapy.utils.project.inside_project', return_value=True)
    def test_get_project_path(self, mock_ip):
        def _test(settingsmod, expected):
            with mock.patch.dict('os.environ',
                                 {'SCRAPY_SETTINGS_MODULE': settingsmod}):
                self.assertEqual(get_project_path(), expected)
        _test('project.settings', 'project')
        _test('project.othername', 'project')
        _test('nested.project.settings', 'nested.project')

        with mock.patch.dict('os.environ', {}, clear=True):
            self.assertRaises(NotConfigured, get_project_path)

        mock_ip.return_value = False
        with mock.patch.dict('os.environ',
                             {'SCRAPY_SETTINGS_MODULE': 'some.settings'}):
            self.assertRaises(NotConfigured, get_project_path)
