# Copyright (C) 2007 Giampaolo Rodola' <g.rodola@gmail.com>.
# Use of this source code is governed by MIT license that can be
# found in the LICENSE file.

"""Unit test runner, providing additional features on top of unittest
module:
- colourized output
- print failures/tracebacks on CTRL+C
- re-run failed tests only (make test-failed).

Invocation examples:
- make test
- make test-failed
"""

from __future__ import print_function

import optparse
import os
import sys
import unittest

from pyftpdlib._compat import super
from pyftpdlib.test import CI_TESTING
from pyftpdlib.test import POSIX
from pyftpdlib.test import configure_logging
from pyftpdlib.test import safe_rmpath


VERBOSITY = 2
FAILED_TESTS_FNAME = '.failed-tests.txt'
HERE = os.path.abspath(os.path.dirname(__file__))
loadTestsFromTestCase = unittest.defaultTestLoader.loadTestsFromTestCase  # noqa


def term_supports_colors(file=sys.stdout):  # pragma: no cover
    if os.name == 'nt':
        return True
    try:
        import curses
        assert file.isatty()
        curses.setupterm()
        assert curses.tigetnum("colors") > 0
    except Exception:
        return False
    else:
        return True


USE_COLORS = not CI_TESTING and term_supports_colors()


def print_color(
        s, color=None, bold=False, file=sys.stdout):  # pragma: no cover
    """Print a colorized version of string."""
    if not term_supports_colors():
        print(s, file=file)  # NOQA
    elif POSIX:
        print(hilite(s, color, bold), file=file)  # NOQA
    else:
        import ctypes

        DEFAULT_COLOR = 7
        GetStdHandle = ctypes.windll.Kernel32.GetStdHandle
        SetConsoleTextAttribute = \
            ctypes.windll.Kernel32.SetConsoleTextAttribute

        colors = dict(green=2, red=4, brown=6, yellow=6)
        colors[None] = DEFAULT_COLOR
        try:
            color = colors[color]
        except KeyError:
            raise ValueError("invalid color %r; choose between %r" % (
                color, list(colors.keys())))
        if bold and color <= 7:
            color += 8

        handle_id = -12 if file is sys.stderr else -11
        GetStdHandle.restype = ctypes.c_ulong
        handle = GetStdHandle(handle_id)
        SetConsoleTextAttribute(handle, color)
        try:
            print(s, file=file)    # NOQA
        finally:
            SetConsoleTextAttribute(handle, DEFAULT_COLOR)



def hilite(s, color=None, bold=False):  # pragma: no cover
    """Return an highlighted version of 'string'."""
    if not term_supports_colors():
        return s
    attr = []
    colors = dict(green='32', red='91', brown='33', yellow='93', blue='34',
                  violet='35', lightblue='36', grey='37', darkgrey='30')
    colors[None] = '29'
    try:
        color = colors[color]
    except KeyError:
        raise ValueError("invalid color %r; choose between %s" % (
            list(colors.keys())))
    attr.append(color)
    if bold:
        attr.append('1')
    return '\x1b[%sm%s\x1b[0m' % (';'.join(attr), s)


def import_module_by_path(path):
    name = os.path.splitext(os.path.basename(path))[0]
    if sys.version_info[0] < 3:
        import imp
        return imp.load_source(name, path)
    else:
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


def cprint(msg, color, bold=False, file=None):
    if file is None:
        file = sys.stderr if color == 'red' else sys.stdout
    if USE_COLORS:
        print_color(msg, color, bold=bold, file=file)
    else:
        print(msg, file=file)


class TestLoader:

    testdir = HERE
    skip_files = []

    def _get_testmods(self):
        return [os.path.join(self.testdir, x)
                for x in os.listdir(self.testdir)
                if x.startswith('test_') and x.endswith('.py') and
                x not in self.skip_files]

    def _iter_testmod_classes(self):
        """Iterate over all test files in this directory and return
        all TestCase classes in them.
        """
        for path in self._get_testmods():
            mod = import_module_by_path(path)
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and \
                        issubclass(obj, unittest.TestCase):
                    yield obj

    def all(self):
        suite = unittest.TestSuite()
        for obj in self._iter_testmod_classes():
            test = loadTestsFromTestCase(obj)
            suite.addTest(test)
        return suite

    def last_failed(self):
        # ...from previously failed test run
        suite = unittest.TestSuite()
        if not os.path.isfile(FAILED_TESTS_FNAME):
            return suite
        with open(FAILED_TESTS_FNAME) as f:
            names = f.read().split()
        for n in names:
            test = unittest.defaultTestLoader.loadTestsFromName(n)
            suite.addTest(test)
        return suite

    def from_name(self, name):
        if name.endswith('.py'):
            name = os.path.splitext(os.path.basename(name))[0]
        return unittest.defaultTestLoader.loadTestsFromName(name)


class ColouredResult(unittest.TextTestResult):

    def addSuccess(self, test):
        unittest.TestResult.addSuccess(self, test)
        cprint("OK", "green")

    def addError(self, test, err):
        unittest.TestResult.addError(self, test, err)
        cprint("ERROR", "red", bold=True)

    def addFailure(self, test, err):
        unittest.TestResult.addFailure(self, test, err)
        cprint("FAIL", "red")

    def addSkip(self, test, reason):
        unittest.TestResult.addSkip(self, test, reason)
        cprint("skipped: %s" % reason.strip(), "brown")

    def printErrorList(self, flavour, errors):
        flavour = hilite(flavour, "red", bold=flavour == 'ERROR')
        super().printErrorList(flavour, errors)


class ColouredTextRunner(unittest.TextTestRunner):
    """A coloured text runner which also prints failed tests on
    KeyboardInterrupt and save failed tests in a file so that they can
    be re-run.
    """

    resultclass = ColouredResult if USE_COLORS else unittest.TextTestResult

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.failed_tnames = set()

    def _makeResult(self):
        # Store result instance so that it can be accessed on
        # KeyboardInterrupt.
        self.result = super()._makeResult()
        return self.result

    def _write_last_failed(self):
        if self.failed_tnames:
            with open(FAILED_TESTS_FNAME, "w") as f:
                for tname in self.failed_tnames:
                    f.write(tname + '\n')

    def _save_result(self, result):
        if not result.wasSuccessful():
            for t in result.errors + result.failures:
                tname = t[0].id()
                self.failed_tnames.add(tname)

    def _run(self, suite):
        try:
            result = super().run(suite)
        except (KeyboardInterrupt, SystemExit):
            result = self.runner.result
            result.printErrors()
            raise sys.exit(1)
        else:
            self._save_result(result)
            return result

    def _exit(self, success):
        if success:
            cprint("SUCCESS", "green", bold=True)
            safe_rmpath(FAILED_TESTS_FNAME)
            sys.exit(0)
        else:
            cprint("FAILED", "red", bold=True)
            self._write_last_failed()
            sys.exit(1)

    def run(self, suite):
        result = self._run(suite)
        self._exit(result.wasSuccessful())


def setup():
    configure_logging()


# Used by test_*,py modules.
def run_from_name(name):
    setup()
    suite = TestLoader().from_name(name)
    runner = ColouredTextRunner(verbosity=VERBOSITY)
    runner.run(suite)


def main():
    usage = "python3 -m pyftpdlib.test [opts] [test-name]"
    parser = optparse.OptionParser(usage=usage, description="run unit tests")
    parser.add_option("--last-failed",
                      action="store_true", default=False,
                      help="only run last failed tests")
    opts, args = parser.parse_args()

    if not opts.last_failed:
        safe_rmpath(FAILED_TESTS_FNAME)

    # loader
    loader = TestLoader()
    if args:
        if len(args) > 1:
            parser.print_usage()
            return sys.exit(1)
        else:
            suite = loader.from_name(args[0])
    elif opts.last_failed:
        suite = loader.last_failed()
    else:
        suite = loader.all()

    setup()
    runner = ColouredTextRunner(verbosity=VERBOSITY)
    runner.run(suite)


if __name__ == '__main__':
    main()
