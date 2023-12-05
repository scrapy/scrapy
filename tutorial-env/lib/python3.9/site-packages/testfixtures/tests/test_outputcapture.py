import sys
from subprocess import call
from unittest import TestCase

from testfixtures import OutputCapture, compare
from .test_compare import CompareHelper


class TestOutputCapture(CompareHelper, TestCase):

    def test_compare_strips(self):
        with OutputCapture() as o:
            print(' Bar! ')
        o.compare('Bar!')

    def test_compare_doesnt_strip(self):
        with OutputCapture(strip_whitespace=False) as o:
            print(' Bar! ')
        self.check_raises(
            '\tBar!',
            compare=o.compare,
            message="'\\tBar!' (expected) != ' Bar! \\n' (actual)",
        )

    def test_stdout_and_stderr(self):
        with OutputCapture() as o:
            print('hello', file=sys.stdout)
            print('out', file=sys.stderr)
            print('there', file=sys.stdout)
            print('now', file=sys.stderr)
        o.compare("hello\nout\nthere\nnow\n")

    def test_unicode(self):
        with OutputCapture() as o:
            print(u'\u65e5', file=sys.stdout)
        o.compare(u'\u65e5\n')

    def test_separate_capture(self):
        with OutputCapture(separate=True) as o:
            print('hello', file=sys.stdout)
            print('out', file=sys.stderr)
            print('there', file=sys.stdout)
            print('now', file=sys.stderr)
        o.compare(stdout="hello\nthere\n",
                  stderr="out\nnow\n")

    def test_compare_both_at_once(self):
        with OutputCapture(separate=True) as o:
            print('hello', file=sys.stdout)
            print('out', file=sys.stderr)
        self.check_raises(
            stdout="out\n",
            stderr="hello\n",
            compare=o.compare,
            message=(
                'dict not as expected:\n'
                '\n'
                'values differ:\n'
                "'stderr': 'hello' (expected) != 'out' (actual)\n"
                "'stdout': 'out' (expected) != 'hello' (actual)\n"
                '\n'
                "While comparing ['stderr']: 'hello' (expected) != 'out' (actual)\n"
                '\n'
                "While comparing ['stdout']: 'out' (expected) != 'hello' (actual)"
            ),
        )

    def test_original_restore(self):
        o_out, o_err = sys.stdout, sys.stderr
        with OutputCapture() as o:
            self.assertFalse(sys.stdout is o_out)
            self.assertFalse(sys.stderr is o_err)
        self.assertTrue(sys.stdout is o_out)
        self.assertTrue(sys.stderr is o_err)

    def test_double_disable(self):
        o_out, o_err = sys.stdout, sys.stderr
        with OutputCapture() as o:
            self.assertFalse(sys.stdout is o_out)
            self.assertFalse(sys.stderr is o_err)
            o.disable()
            self.assertTrue(sys.stdout is o_out)
            self.assertTrue(sys.stderr is o_err)
            o.disable()
            self.assertTrue(sys.stdout is o_out)
            self.assertTrue(sys.stderr is o_err)
        self.assertTrue(sys.stdout is o_out)
        self.assertTrue(sys.stderr is o_err)

    def test_double_enable(self):
        o_out, o_err = sys.stdout, sys.stderr
        with OutputCapture() as o:
            o.disable()
            self.assertTrue(sys.stdout is o_out)
            self.assertTrue(sys.stderr is o_err)
            o.enable()
            self.assertFalse(sys.stdout is o_out)
            self.assertFalse(sys.stderr is o_err)
            o.enable()
            self.assertFalse(sys.stdout is o_out)
            self.assertFalse(sys.stderr is o_err)
        self.assertTrue(sys.stdout is o_out)
        self.assertTrue(sys.stderr is o_err)


class TestOutputCaptureWithDescriptors(object):

    def test_fd(self, capfd):
        with capfd.disabled(), OutputCapture(fd=True) as o:
            call([sys.executable, '-c', "import sys; sys.stdout.write('out')"])
            call([sys.executable, '-c', "import sys; sys.stderr.write('err')"])
        compare(o.captured, expected='outerr')
        o.compare(expected='outerr')

    def test_fd_separate(self, capfd):
        with capfd.disabled(), OutputCapture(fd=True, separate=True) as o:
            call([sys.executable, '-c', "import sys; sys.stdout.write('out')"])
            call([sys.executable, '-c', "import sys; sys.stderr.write('err')"])
        compare(o.captured, expected='')
        o.compare(stdout='out', stderr='err')
