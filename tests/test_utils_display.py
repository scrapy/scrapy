import sys

from unittest import mock, TestCase

from scrapy.utils.display import _colorize, _color_support_info


class TestDisplay(TestCase):
    if sys.platform != "win32":
        @mock.patch('sys.stdout.isatty', autospec=True)
        def test_color(self, mock_isatty):
            mock_isatty.return_value = True
            if _color_support_info():
                self.assertEqual(
                    _colorize('{"a": 1}'),
                    '{\x1b[33m"\x1b[39;49;00m\x1b[33ma\x1b[39;49;00m\x1b[33m"\x1b[39;49;00m: \x1b[34m1\x1b[39;49;00m}\n'
                )
            else:
                self.assertEqual(_colorize('{"a": 1}'), '{"a": 1}')
    else:
        @mock.patch('sys.platform', 'win32')
        @mock.patch('ctypes.windll')
        def test_color_windows(self, mock_ctypes):
            mock_ctypes.kernel32.GetStdHandle.return_value = -11
            with mock.patch('sys.stdout.isatty', autospec=True) as mock_isatty:
                mock_isatty.return_value = True
                if _color_support_info():
                    self.assertEqual(
                        _colorize('{"a": 1}'),
                        '{\x1b[33m"\x1b[39;49;00m\x1b[33ma\x1b[39;49;00m\x1b[33m"\x1b[39;49;00m: \x1b[34m1\x1b[39;49;00m}\n'
                    )
