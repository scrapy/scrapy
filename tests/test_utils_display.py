from unittest import mock, TestCase

from scrapy.utils.display import _colorize, _color_support_info


class TestDisplay(TestCase):

    @mock.patch('sys.stdout.isatty', autospec=True)
    def test_color(self, mock_isatty):
        mock_isatty.return_value = True
        if _color_support_info() == 256:
            self.assertEqual(
                _colorize('{"a": 1}'),
                '{\x1b[38;5;124m"\x1b[39m\x1b[38;5;124ma\x1b[39m\x1b[38;5;124m"\x1b[39m: \x1b[38;5;241m1\x1b[39m}\n'
            )
        else:
            self.assertEqual(
                _colorize('{"a": 1}'),
                '{\x1b[33m"\x1b[39;49;00m\x1b[33ma\x1b[39;49;00m\x1b[33m"\x1b[39;49;00m: \x1b[94m1\x1b[39;49;00m}\n'
            )
