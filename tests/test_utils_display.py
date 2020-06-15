import sys

from io import StringIO

from unittest import mock, TestCase

from scrapy.utils.display import _colorize, _color_support_info, pformat, pprint

TestStr = "{\x1b[33m'\x1b[39;49;00m\x1b[33ma\x1b[39;49;00m\x1b[33m'\x1b[39;49;00m: \x1b[34m1\x1b[39;49;00m}\n"


class TestDisplay(TestCase):
    if sys.platform != "win32":
        @mock.patch('sys.stdout.isatty', autospec=True)
        def test_color(self, mock_isatty):
            mock_isatty.return_value = True
            if _color_support_info():
                self.assertEqual(pformat({'a': 1}), TestStr)

            with mock.patch("scrapy.utils.display._color_support_info") as mock_color:
                mock_color.return_value = False
                self.assertEqual(_colorize("{'a': 1}"), "{'a': 1}")

                mock_color.return_value = True
                self.assertEqual(_colorize("{'a': 1}"), TestStr)

            sys.modules["curses"] = None
            self.assertEqual(_colorize("{'a': 1}"), TestStr)

            sys.modules["pygments"] = None
            self.assertEqual(_colorize("{'a': 1}"), "{'a': 1}")

            mock_isatty.return_value = False
            self.assertEqual(_colorize("{'a': 1}"), "{'a': 1}")

    @mock.patch('sys.platform', mock.MagicMock(return_value="win32"))
    @mock.patch('ctypes.windll')
    def test_color_windows(self, mock_ctypes):
        mock_ctypes.kernel32.GetStdHandle.return_value = -11
        with mock.patch('sys.stdout.isatty', autospec=True) as mock_isatty:
            mock_isatty.return_value = True
            if _color_support_info():
                self.assertEqual(pformat({'a': 1}), TestStr)

            with mock.patch("scrapy.utils.display._color_support_info") as mock_color:
                mock_color.return_value = False
                self.assertEqual(_colorize("{'a': 1}"), "{'a': 1}")

                mock_color.return_value = True
                self.assertEqual(_colorize("{'a': 1}"), TestStr)

            sys.modules["pygments"] = None
            self.assertEqual(_colorize("{'a': 1}"), "{'a': 1}")

            sys.modules["ctypes"] = None
            self.assertEqual(_colorize("{'a': 1}"), "{'a': 1}")

            mock_isatty.return_value = False
            self.assertEqual(_colorize("{'a': 1}"), "{'a': 1}")

    def test_stdout(self):
        with mock.patch('sys.stdout', new=StringIO()) as mock_out:
            pprint("{'a': 1}")
            self.assertEqual(mock_out.getvalue(), '"{\'a\': 1}"\n')
