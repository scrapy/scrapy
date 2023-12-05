import sys
import unittest

from unittest import mock
from bpython.curtsiesfrontend.coderunner import CodeRunner, FakeOutput


class TestCodeRunner(unittest.TestCase):
    def setUp(self):
        self.orig_stdout = sys.stdout
        self.orig_stderr = sys.stderr

    def tearDown(self):
        sys.stdout = self.orig_stdout
        sys.stderr = self.orig_stderr

    def test_simple(self):
        c = CodeRunner(
            request_refresh=lambda: self.orig_stdout.flush()
            or self.orig_stderr.flush()
        )
        stdout = FakeOutput(c, lambda *args, **kwargs: None, None)
        stderr = FakeOutput(c, lambda *args, **kwargs: None, None)
        sys.stdout = stdout
        sys.stdout = stderr
        c.load_code("1 + 1")
        c.run_code()
        c.run_code()
        c.run_code()

    def test_exception(self):
        c = CodeRunner(
            request_refresh=lambda: self.orig_stdout.flush()
            or self.orig_stderr.flush()
        )

        def ctrlc():
            raise KeyboardInterrupt()

        stdout = FakeOutput(c, lambda x: ctrlc(), None)
        stderr = FakeOutput(c, lambda *args, **kwargs: None, None)
        sys.stdout = stdout
        sys.stderr = stderr
        c.load_code("1 + 1")
        c.run_code()


class TestFakeOutput(unittest.TestCase):
    def assert_unicode(self, s):
        self.assertIsInstance(s, str)

    def test_bytes(self):
        out = FakeOutput(mock.Mock(), self.assert_unicode, None)
        out.write("native string type")
