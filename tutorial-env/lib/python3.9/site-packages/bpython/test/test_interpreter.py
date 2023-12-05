import sys
import re
import unittest

from curtsies.fmtfuncs import bold, green, magenta, cyan, red, plain
from unittest import mock

from bpython.curtsiesfrontend import interpreter

pypy = "PyPy" in sys.version


def remove_ansi(s):
    return re.sub(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]".encode("ascii"), b"", s)


class TestInterpreter(unittest.TestCase):
    def interp_errlog(self):
        i = interpreter.Interp()
        a = []
        i.write = a.append
        return i, a

    def err_lineno(self, a):
        strings = [x.__unicode__() for x in a]
        for line in reversed(strings):
            clean_line = remove_ansi(line)
            m = re.search(r"line (\d+)[,]", clean_line)
            if m:
                return int(m.group(1))
        return None

    def test_syntaxerror(self):
        i, a = self.interp_errlog()

        i.runsource("1.1.1.1")

        if (3, 10, 1) <= sys.version_info[:3]:
            expected = (
                "  File "
                + green('"<input>"')
                + ", line "
                + bold(magenta("1"))
                + "\n    1.1.1.1\n       ^^\n"
                + bold(red("SyntaxError"))
                + ": "
                + cyan("invalid syntax")
                + "\n"
            )
        elif (3, 10) <= sys.version_info[:2]:
            expected = (
                "  File "
                + green('"<input>"')
                + ", line "
                + bold(magenta("1"))
                + "\n    1.1.1.1\n    ^^^^^\n"
                + bold(red("SyntaxError"))
                + ": "
                + cyan("invalid syntax. Perhaps you forgot a comma?")
                + "\n"
            )
        elif (3, 8) <= sys.version_info[:2]:
            expected = (
                "  File "
                + green('"<input>"')
                + ", line "
                + bold(magenta("1"))
                + "\n    1.1.1.1\n       ^\n"
                + bold(red("SyntaxError"))
                + ": "
                + cyan("invalid syntax")
                + "\n"
            )
        elif pypy:
            expected = (
                "  File "
                + green('"<input>"')
                + ", line "
                + bold(magenta("1"))
                + "\n    1.1.1.1\n       ^\n"
                + bold(red("SyntaxError"))
                + ": "
                + cyan("invalid syntax")
                + "\n"
            )
        else:
            expected = (
                "  File "
                + green('"<input>"')
                + ", line "
                + bold(magenta("1"))
                + "\n    1.1.1.1\n        ^\n"
                + bold(red("SyntaxError"))
                + ": "
                + cyan("invalid syntax")
                + "\n"
            )

        self.assertMultiLineEqual(str(plain("").join(a)), str(expected))
        self.assertEqual(plain("").join(a), expected)

    def test_traceback(self):
        i, a = self.interp_errlog()

        def f():
            return 1 / 0

        def gfunc():
            return f()

        i.runsource("gfunc()")

        global_not_found = "name 'gfunc' is not defined"

        if (3, 11) <= sys.version_info[:2]:
            expected = (
                "Traceback (most recent call last):\n  File "
                + green('"<input>"')
                + ", line "
                + bold(magenta("1"))
                + ", in "
                + cyan("<module>")
                + "\n    gfunc()"
                + "\n     ^^^^^\n"
                + bold(red("NameError"))
                + ": "
                + cyan(global_not_found)
                + "\n"
            )
        else:
            expected = (
                "Traceback (most recent call last):\n  File "
                + green('"<input>"')
                + ", line "
                + bold(magenta("1"))
                + ", in "
                + cyan("<module>")
                + "\n    gfunc()\n"
                + bold(red("NameError"))
                + ": "
                + cyan(global_not_found)
                + "\n"
            )

        self.assertMultiLineEqual(str(plain("").join(a)), str(expected))
        self.assertEqual(plain("").join(a), expected)

    def test_getsource_works_on_interactively_defined_functions(self):
        source = "def foo(x):\n    return x + 1\n"
        i = interpreter.Interp()
        i.runsource(source)
        import inspect

        inspected_source = inspect.getsource(i.locals["foo"])
        self.assertEqual(inspected_source, source)
