import builtins
from io import StringIO
from unittest import mock

from scrapy.utils.display import pformat, pprint

value = {"a": 1}
colorized_strings = {
    (
        (
            "{\x1b[33m'\x1b[39;49;00m\x1b[33ma\x1b[39;49;00m\x1b[33m'"
            "\x1b[39;49;00m: \x1b[34m1\x1b[39;49;00m}"
        )
        + suffix
    )
    for suffix in (
        # https://github.com/pygments/pygments/issues/2313
        "\n",  # pygments ≤ 2.13
        "\x1b[37m\x1b[39;49;00m\n",  # pygments ≥ 2.14
    )
}
plain_string = "{'a': 1}"


@mock.patch("sys.platform", "linux")
@mock.patch("sys.stdout.isatty")
def test_pformat(isatty):
    isatty.return_value = True
    assert pformat(value) in colorized_strings


@mock.patch("sys.stdout.isatty")
def test_pformat_dont_colorize(isatty):
    isatty.return_value = True
    assert pformat(value, colorize=False) == plain_string


def test_pformat_not_tty():
    assert pformat(value) == plain_string


@mock.patch("sys.platform", "win32")
@mock.patch("platform.version")
@mock.patch("sys.stdout.isatty")
def test_pformat_old_windows(isatty, version):
    isatty.return_value = True
    version.return_value = "10.0.14392"
    assert pformat(value) in colorized_strings


@mock.patch("sys.platform", "win32")
@mock.patch("scrapy.utils.display._enable_windows_terminal_processing")
@mock.patch("platform.version")
@mock.patch("sys.stdout.isatty")
def test_pformat_windows_no_terminal_processing(isatty, version, terminal_processing):
    isatty.return_value = True
    version.return_value = "10.0.14393"
    terminal_processing.return_value = False
    assert pformat(value) == plain_string


@mock.patch("sys.platform", "win32")
@mock.patch("scrapy.utils.display._enable_windows_terminal_processing")
@mock.patch("platform.version")
@mock.patch("sys.stdout.isatty")
def test_pformat_windows(isatty, version, terminal_processing):
    isatty.return_value = True
    version.return_value = "10.0.14393"
    terminal_processing.return_value = True
    assert pformat(value) in colorized_strings


@mock.patch("sys.platform", "linux")
@mock.patch("sys.stdout.isatty")
def test_pformat_no_pygments(isatty):
    isatty.return_value = True

    real_import = builtins.__import__

    def mock_import(name, globals_, locals_, fromlist, level):
        if "pygments" in name:
            raise ImportError
        return real_import(name, globals_, locals_, fromlist, level)

    builtins.__import__ = mock_import
    assert pformat(value) == plain_string
    builtins.__import__ = real_import


def test_pprint():
    with mock.patch("sys.stdout", new=StringIO()) as mock_out:
        pprint(value)
        assert mock_out.getvalue() == "{'a': 1}\n"
