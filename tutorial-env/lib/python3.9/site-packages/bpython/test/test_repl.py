import collections
import inspect
import socket
import sys
import tempfile
import unittest

from typing import List, Tuple
from itertools import islice
from pathlib import Path
from unittest import mock

from bpython import config, repl, cli, autocomplete
from bpython.line import LinePart
from bpython.test import (
    MagicIterMock,
    FixLanguageTestCase as TestCase,
    TEST_CONFIG,
)


pypy = "PyPy" in sys.version


def setup_config(conf):
    config_struct = config.Config(TEST_CONFIG)
    if conf is not None and "autocomplete_mode" in conf:
        config_struct.autocomplete_mode = conf["autocomplete_mode"]
    return config_struct


class FakeHistory(repl.History):
    def __init__(self):
        pass

    def reset(self):
        pass


class FakeRepl(repl.Repl):
    def __init__(self, conf=None):
        super().__init__(repl.Interpreter(), setup_config(conf))
        self._current_line = ""
        self._cursor_offset = 0

    def _get_current_line(self) -> str:
        return self._current_line

    def _set_current_line(self, val: str) -> None:
        self._current_line = val

    def _get_cursor_offset(self) -> int:
        return self._cursor_offset

    def _set_cursor_offset(self, val: int) -> None:
        self._cursor_offset = val

    def getstdout(self) -> str:
        raise NotImplementedError

    def reprint_line(
        self, lineno: int, tokens: List[Tuple[repl._TokenType, str]]
    ) -> None:
        raise NotImplementedError

    def reevaluate(self):
        raise NotImplementedError


class FakeCliRepl(cli.CLIRepl, FakeRepl):
    def __init__(self):
        self.s = ""
        self.cpos = 0
        self.rl_history = FakeHistory()


class TestMatchesIterator(unittest.TestCase):
    def setUp(self):
        self.matches = ["bobby", "bobbies", "bobberina"]
        self.matches_iterator = repl.MatchesIterator()
        self.matches_iterator.current_word = "bob"
        self.matches_iterator.orig_line = "bob"
        self.matches_iterator.orig_cursor_offset = len("bob")
        self.matches_iterator.matches = self.matches

    def test_next(self):
        self.assertEqual(next(self.matches_iterator), self.matches[0])

        for x in range(len(self.matches) - 1):
            next(self.matches_iterator)

        self.assertEqual(next(self.matches_iterator), self.matches[0])
        self.assertEqual(next(self.matches_iterator), self.matches[1])
        self.assertNotEqual(next(self.matches_iterator), self.matches[1])

    def test_previous(self):
        self.assertEqual(self.matches_iterator.previous(), self.matches[2])

        for x in range(len(self.matches) - 1):
            self.matches_iterator.previous()

        self.assertNotEqual(self.matches_iterator.previous(), self.matches[0])
        self.assertEqual(self.matches_iterator.previous(), self.matches[1])
        self.assertEqual(self.matches_iterator.previous(), self.matches[0])

    def test_nonzero(self):
        """self.matches_iterator should be False at start,
        then True once we active a match.
        """
        self.assertFalse(self.matches_iterator)
        next(self.matches_iterator)
        self.assertTrue(self.matches_iterator)

    def test_iter(self):
        slice = islice(self.matches_iterator, 0, 9)
        self.assertEqual(list(slice), self.matches * 3)

    def test_current(self):
        with self.assertRaises(ValueError):
            self.matches_iterator.current()
        next(self.matches_iterator)
        self.assertEqual(self.matches_iterator.current(), self.matches[0])

    def test_update(self):
        slice = islice(self.matches_iterator, 0, 3)
        self.assertEqual(list(slice), self.matches)

        newmatches = ["string", "str", "set"]
        completer = mock.Mock()
        completer.locate.return_value = LinePart(0, 1, "s")
        self.matches_iterator.update(1, "s", newmatches, completer)

        newslice = islice(newmatches, 0, 3)
        self.assertNotEqual(list(slice), self.matches)
        self.assertEqual(list(newslice), newmatches)

    def test_cur_line(self):
        completer = mock.Mock()
        completer.locate.return_value = LinePart(
            0,
            self.matches_iterator.orig_cursor_offset,
            self.matches_iterator.orig_line,
        )
        self.matches_iterator.completer = completer

        with self.assertRaises(ValueError):
            self.matches_iterator.cur_line()

        self.assertEqual(next(self.matches_iterator), self.matches[0])
        self.assertEqual(
            self.matches_iterator.cur_line(),
            (len(self.matches[0]), self.matches[0]),
        )

    def test_is_cseq(self):
        self.assertTrue(self.matches_iterator.is_cseq())


class TestArgspec(unittest.TestCase):
    def setUp(self):
        self.repl = FakeRepl()
        self.repl.push("def spam(a, b, c):\n", False)
        self.repl.push("    pass\n", False)
        self.repl.push("\n", False)
        self.repl.push("class Spam(object):\n", False)
        self.repl.push("    def spam(self, a, b, c):\n", False)
        self.repl.push("        pass\n", False)
        self.repl.push("\n", False)
        self.repl.push("class SpammitySpam(object):\n", False)
        self.repl.push("    def __init__(self, a, b, c):\n", False)
        self.repl.push("        pass\n", False)
        self.repl.push("\n", False)
        self.repl.push("class WonderfulSpam(object):\n", False)
        self.repl.push("    def __new__(self, a, b, c):\n", False)
        self.repl.push("        pass\n", False)
        self.repl.push("\n", False)
        self.repl.push("o = Spam()\n", False)
        self.repl.push("\n", False)

    def set_input_line(self, line):
        """Set current input line of the test REPL."""
        self.repl.current_line = line
        self.repl.cursor_offset = len(line)

    def test_func_name(self):
        for (line, expected_name) in [
            ("spam(", "spam"),
            # map pydoc has no signature in pypy
            ("spam(any([]", "any") if pypy else ("spam(map([]", "map"),
            ("spam((), ", "spam"),
        ]:
            self.set_input_line(line)
            self.assertTrue(self.repl.get_args())
            self.assertEqual(self.repl.current_func.__name__, expected_name)

    def test_func_name_method_issue_479(self):
        for (line, expected_name) in [
            ("o.spam(", "spam"),
            # map pydoc has no signature in pypy
            ("o.spam(any([]", "any") if pypy else ("o.spam(map([]", "map"),
            ("o.spam((), ", "spam"),
        ]:
            self.set_input_line(line)
            self.assertTrue(self.repl.get_args())
            self.assertEqual(self.repl.current_func.__name__, expected_name)

    def test_syntax_error_parens(self):
        for line in ["spam(]", "spam([)", "spam())"]:
            self.set_input_line(line)
            # Should not explode
            self.repl.get_args()

    def test_kw_arg_position(self):
        self.set_input_line("spam(a=0")
        self.assertTrue(self.repl.get_args())
        self.assertEqual(self.repl.arg_pos, "a")

        self.set_input_line("spam(1, b=1")
        self.assertTrue(self.repl.get_args())
        self.assertEqual(self.repl.arg_pos, "b")

        self.set_input_line("spam(1, c=2")
        self.assertTrue(self.repl.get_args())
        self.assertEqual(self.repl.arg_pos, "c")

    def test_lambda_position(self):
        self.set_input_line("spam(lambda a, b: 1, ")
        self.assertTrue(self.repl.get_args())
        self.assertTrue(self.repl.funcprops)
        # Argument position
        self.assertEqual(self.repl.arg_pos, 1)

    @unittest.skipIf(pypy, "range pydoc has no signature in pypy")
    def test_issue127(self):
        self.set_input_line("x=range(")
        self.assertTrue(self.repl.get_args())
        self.assertEqual(self.repl.current_func.__name__, "range")

        self.set_input_line("{x:range(")
        self.assertTrue(self.repl.get_args())
        self.assertEqual(self.repl.current_func.__name__, "range")

        self.set_input_line("foo(1, 2, x,range(")
        self.assertEqual(self.repl.current_func.__name__, "range")

        self.set_input_line("(x,range(")
        self.assertEqual(self.repl.current_func.__name__, "range")

    def test_nonexistent_name(self):
        self.set_input_line("spamspamspam(")
        self.assertFalse(self.repl.get_args())

    def test_issue572(self):
        self.set_input_line("SpammitySpam(")
        self.assertTrue(self.repl.get_args())

        self.set_input_line("WonderfulSpam(")
        self.assertTrue(self.repl.get_args())

    @unittest.skipIf(pypy, "pypy pydoc doesn't have this")
    def test_issue583(self):
        self.repl = FakeRepl()
        self.repl.push("a = 1.2\n", False)
        self.set_input_line("a.is_integer(")
        self.repl.set_docstring()
        self.assertIsNot(self.repl.docstring, None)

    def test_methods_of_expressions(self):
        self.set_input_line("'a'.capitalize(")
        self.assertTrue(self.repl.get_args())

        self.set_input_line("(1 + 1.1).as_integer_ratio(")
        self.assertTrue(self.repl.get_args())


class TestArgspecInternal(unittest.TestCase):
    def test_function_expressions(self):
        te = self.assertTupleEqual
        fa = lambda line: repl.Repl._funcname_and_argnum(line)
        for line, (func, argnum) in [
            ("spam(", ("spam", 0)),
            ("spam((), ", ("spam", 1)),
            ("spam.eggs((), ", ("spam.eggs", 1)),
            ("spam[abc].eggs((), ", ("spam[abc].eggs", 1)),
            ("spam[0].eggs((), ", ("spam[0].eggs", 1)),
            ("spam[a + b]eggs((), ", ("spam[a + b]eggs", 1)),
            ("spam().eggs((), ", ("spam().eggs", 1)),
            ("spam(1, 2).eggs((), ", ("spam(1, 2).eggs", 1)),
            ("spam(1, f(1)).eggs((), ", ("spam(1, f(1)).eggs", 1)),
            ("[0].eggs((), ", ("[0].eggs", 1)),
            ("[0][0]((), {}).eggs((), ", ("[0][0]((), {}).eggs", 1)),
            ("a + spam[0].eggs((), ", ("spam[0].eggs", 1)),
            ("spam(", ("spam", 0)),
            ("spam(map([]", ("map", 0)),
            ("spam((), ", ("spam", 1)),
        ]:
            te(fa(line), (func, argnum))


class TestGetSource(unittest.TestCase):
    def setUp(self):
        self.repl = FakeRepl()

    def set_input_line(self, line):
        """Set current input line of the test REPL."""
        self.repl.current_line = line
        self.repl.cursor_offset = len(line)

    def assert_get_source_error_for_current_function(self, func, msg):
        self.repl.current_func = func
        with self.assertRaises(repl.SourceNotFound):
            self.repl.get_source_of_current_name()
        try:
            self.repl.get_source_of_current_name()
        except repl.SourceNotFound as e:
            self.assertEqual(e.args[0], msg)
        else:
            self.fail("Should have raised SourceNotFound")

    def test_current_function(self):
        self.set_input_line("INPUTLINE")
        self.repl.current_func = inspect.getsource
        self.assertIn(
            "text of the source code", self.repl.get_source_of_current_name()
        )

        self.assert_get_source_error_for_current_function(
            [], "No source code found for INPUTLINE"
        )

        self.assert_get_source_error_for_current_function(
            list.pop, "No source code found for INPUTLINE"
        )

    @unittest.skipIf(pypy, "different errors for PyPy")
    def test_current_function_cpython(self):
        self.set_input_line("INPUTLINE")
        self.assert_get_source_error_for_current_function(
            collections.defaultdict.copy, "No source code found for INPUTLINE"
        )
        self.assert_get_source_error_for_current_function(
            collections.defaultdict, "could not find class definition"
        )

    def test_current_line(self):
        self.repl.interp.locals["a"] = socket.socket
        self.set_input_line("a")
        self.assertIn("dup(self)", self.repl.get_source_of_current_name())


# TODO add tests for various failures without using current function


class TestEditConfig(TestCase):
    def setUp(self):
        self.repl = FakeRepl()
        self.repl.interact.confirm = lambda msg: True
        self.repl.interact.notify = lambda msg: None
        self.repl.config.editor = "true"

    def test_create_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "newdir" / "config"
            self.repl.config.config_path = config_path
            self.repl.edit_config()
            self.assertTrue(config_path.exists())


class TestRepl(unittest.TestCase):
    def set_input_line(self, line):
        """Set current input line of the test REPL."""
        self.repl.current_line = line
        self.repl.cursor_offset = len(line)

    def setUp(self):
        self.repl = FakeRepl()

    def test_current_string(self):
        self.set_input_line('a = "2"')
        # TODO factor cpos out of repl.Repl
        self.repl.cpos = 0
        self.assertEqual(self.repl.current_string(), '"2"')

        self.set_input_line('a = "2" + 2')
        self.assertEqual(self.repl.current_string(), "")

    def test_push(self):
        self.repl = FakeRepl()
        self.repl.push("foobar = 2")
        self.assertEqual(self.repl.interp.locals["foobar"], 2)

    # COMPLETE TESTS
    # 1. Global tests
    def test_simple_global_complete(self):
        self.repl = FakeRepl(
            {"autocomplete_mode": autocomplete.AutocompleteModes.SIMPLE}
        )
        self.set_input_line("d")

        self.assertTrue(self.repl.complete())
        self.assertTrue(hasattr(self.repl.matches_iter, "matches"))
        self.assertEqual(
            self.repl.matches_iter.matches,
            ["def", "del", "delattr(", "dict(", "dir(", "divmod("],
        )

    def test_substring_global_complete(self):
        self.repl = FakeRepl(
            {"autocomplete_mode": autocomplete.AutocompleteModes.SUBSTRING}
        )
        self.set_input_line("time")

        self.assertTrue(self.repl.complete())
        self.assertTrue(hasattr(self.repl.matches_iter, "matches"))
        self.assertEqual(
            self.repl.matches_iter.matches, ["RuntimeError(", "RuntimeWarning("]
        )

    def test_fuzzy_global_complete(self):
        self.repl = FakeRepl(
            {"autocomplete_mode": autocomplete.AutocompleteModes.FUZZY}
        )
        self.set_input_line("doc")

        self.assertTrue(self.repl.complete())
        self.assertTrue(hasattr(self.repl.matches_iter, "matches"))
        self.assertEqual(
            self.repl.matches_iter.matches,
            ["ChildProcessError(", "UnboundLocalError(", "__doc__"],
        )

    # 2. Attribute tests
    def test_simple_attribute_complete(self):
        self.repl = FakeRepl(
            {"autocomplete_mode": autocomplete.AutocompleteModes.SIMPLE}
        )
        self.set_input_line("Foo.b")

        code = "class Foo():\n\tdef bar(self):\n\t\tpass\n"
        for line in code.split("\n"):
            self.repl.push(line)

        self.assertTrue(self.repl.complete())
        self.assertTrue(hasattr(self.repl.matches_iter, "matches"))
        self.assertEqual(self.repl.matches_iter.matches, ["Foo.bar"])

    def test_substring_attribute_complete(self):
        self.repl = FakeRepl(
            {"autocomplete_mode": autocomplete.AutocompleteModes.SUBSTRING}
        )
        self.set_input_line("Foo.az")

        code = "class Foo():\n\tdef baz(self):\n\t\tpass\n"
        for line in code.split("\n"):
            self.repl.push(line)

        self.assertTrue(self.repl.complete())
        self.assertTrue(hasattr(self.repl.matches_iter, "matches"))
        self.assertEqual(self.repl.matches_iter.matches, ["Foo.baz"])

    def test_fuzzy_attribute_complete(self):
        self.repl = FakeRepl(
            {"autocomplete_mode": autocomplete.AutocompleteModes.FUZZY}
        )
        self.set_input_line("Foo.br")

        code = "class Foo():\n\tdef bar(self):\n\t\tpass\n"
        for line in code.split("\n"):
            self.repl.push(line)

        self.assertTrue(self.repl.complete())
        self.assertTrue(hasattr(self.repl.matches_iter, "matches"))
        self.assertEqual(self.repl.matches_iter.matches, ["Foo.bar"])

    # 3. Edge cases
    def test_updating_namespace_complete(self):
        self.repl = FakeRepl(
            {"autocomplete_mode": autocomplete.AutocompleteModes.SIMPLE}
        )
        self.set_input_line("foo")
        self.repl.push("foobar = 2")

        self.assertTrue(self.repl.complete())
        self.assertTrue(hasattr(self.repl.matches_iter, "matches"))
        self.assertEqual(self.repl.matches_iter.matches, ["foobar"])

    def test_file_should_not_appear_in_complete(self):
        self.repl = FakeRepl(
            {"autocomplete_mode": autocomplete.AutocompleteModes.SIMPLE}
        )
        self.set_input_line("_")
        self.assertTrue(self.repl.complete())
        self.assertTrue(hasattr(self.repl.matches_iter, "matches"))
        self.assertNotIn("__file__", self.repl.matches_iter.matches)

    # 4. Parameter names
    def test_paremeter_name_completion(self):
        self.repl = FakeRepl(
            {"autocomplete_mode": autocomplete.AutocompleteModes.SIMPLE}
        )
        self.set_input_line("foo(ab")

        code = "def foo(abc=1, abd=2, xyz=3):\n\tpass\n"
        for line in code.split("\n"):
            self.repl.push(line)

        self.assertTrue(self.repl.complete())
        self.assertTrue(hasattr(self.repl.matches_iter, "matches"))
        self.assertEqual(
            self.repl.matches_iter.matches, ["abc=", "abd=", "abs("]
        )

    def test_parameter_advanced_on_class(self):
        self.repl = FakeRepl(
            {"autocomplete_mode": autocomplete.AutocompleteModes.SIMPLE}
        )
        self.set_input_line("TestCls(app")

        code = """
        import inspect

        class TestCls:
            # A class with boring __init__ typing
            def __init__(self, *args, **kwargs):
                pass
            # But that uses super exotic typings recognized by inspect.signature
            __signature__ = inspect.Signature([
                inspect.Parameter("apple", inspect.Parameter.POSITIONAL_ONLY),
                inspect.Parameter("apple2", inspect.Parameter.KEYWORD_ONLY),
                inspect.Parameter("pinetree", inspect.Parameter.KEYWORD_ONLY),
            ])
        """
        for line in code.split("\n"):
            print(line[8:])
            self.repl.push(line[8:])

        self.assertTrue(self.repl.complete())
        self.assertTrue(hasattr(self.repl.matches_iter, "matches"))
        self.assertEqual(self.repl.matches_iter.matches, ["apple2=", "apple="])


class TestCliRepl(unittest.TestCase):
    def setUp(self):
        self.repl = FakeCliRepl()

    def test_atbol(self):
        self.assertTrue(self.repl.atbol())

        self.repl.s = "\t\t"
        self.assertTrue(self.repl.atbol())

        self.repl.s = "\t\tnot an empty line"
        self.assertFalse(self.repl.atbol())

    def test_addstr(self):
        self.repl.complete = mock.Mock(True)

        self.repl.s = "foo"
        self.repl.addstr("bar")
        self.assertEqual(self.repl.s, "foobar")

        self.repl.cpos = 3
        self.repl.addstr("buzz")
        self.assertEqual(self.repl.s, "foobuzzbar")


class TestCliReplTab(unittest.TestCase):
    def setUp(self):
        self.repl = FakeCliRepl()

    # 3 Types of tab complete
    def test_simple_tab_complete(self):
        self.repl.matches_iter = MagicIterMock()
        self.repl.matches_iter.__bool__.return_value = False
        self.repl.complete = mock.Mock()
        self.repl.print_line = mock.Mock()
        self.repl.matches_iter.is_cseq.return_value = False
        self.repl.show_list = mock.Mock()
        self.repl.funcprops = mock.Mock()
        self.repl.arg_pos = mock.Mock()
        self.repl.matches_iter.cur_line.return_value = (None, "foobar")

        self.repl.s = "foo"
        self.repl.tab()
        self.assertTrue(self.repl.complete.called)
        self.repl.complete.assert_called_with(tab=True)
        self.assertEqual(self.repl.s, "foobar")

    @unittest.skip("disabled while non-simple completion is disabled")
    def test_substring_tab_complete(self):
        self.repl.s = "bar"
        self.repl.config.autocomplete_mode = (
            autocomplete.AutocompleteModes.FUZZY
        )
        self.repl.tab()
        self.assertEqual(self.repl.s, "foobar")
        self.repl.tab()
        self.assertEqual(self.repl.s, "foofoobar")

    @unittest.skip("disabled while non-simple completion is disabled")
    def test_fuzzy_tab_complete(self):
        self.repl.s = "br"
        self.repl.config.autocomplete_mode = (
            autocomplete.AutocompleteModes.FUZZY
        )
        self.repl.tab()
        self.assertEqual(self.repl.s, "foobar")

    # Edge Cases
    def test_normal_tab(self):
        """make sure pressing the tab key will
        still in some cases add a tab"""
        self.repl.s = ""
        self.repl.config = mock.Mock()
        self.repl.config.tab_length = 4
        self.repl.complete = mock.Mock()
        self.repl.print_line = mock.Mock()
        self.repl.tab()
        self.assertEqual(self.repl.s, "    ")

    def test_back_parameter(self):
        self.repl.matches_iter = mock.Mock()
        self.repl.matches_iter.matches = True
        self.repl.matches_iter.previous.return_value = "previtem"
        self.repl.matches_iter.is_cseq.return_value = False
        self.repl.show_list = mock.Mock()
        self.repl.funcprops = mock.Mock()
        self.repl.arg_pos = mock.Mock()
        self.repl.matches_iter.cur_line.return_value = (None, "previtem")
        self.repl.print_line = mock.Mock()
        self.repl.s = "foo"
        self.repl.cpos = 0
        self.repl.tab(back=True)
        self.assertTrue(self.repl.matches_iter.previous.called)
        self.assertTrue(self.repl.s, "previtem")

    # Attribute Tests
    @unittest.skip("disabled while non-simple completion is disabled")
    def test_fuzzy_attribute_tab_complete(self):
        """Test fuzzy attribute with no text"""
        self.repl.s = "Foo."
        self.repl.config.autocomplete_mode = (
            autocomplete.AutocompleteModes.FUZZY
        )

        self.repl.tab()
        self.assertEqual(self.repl.s, "Foo.foobar")

    @unittest.skip("disabled while non-simple completion is disabled")
    def test_fuzzy_attribute_tab_complete2(self):
        """Test fuzzy attribute with some text"""
        self.repl.s = "Foo.br"
        self.repl.config.autocomplete_mode = (
            autocomplete.AutocompleteModes.FUZZY
        )

        self.repl.tab()
        self.assertEqual(self.repl.s, "Foo.foobar")

    # Expand Tests
    def test_simple_expand(self):
        self.repl.s = "f"
        self.cpos = 0
        self.repl.matches_iter = mock.Mock()
        self.repl.matches_iter.is_cseq.return_value = True
        self.repl.matches_iter.substitute_cseq.return_value = (3, "foo")
        self.repl.print_line = mock.Mock()
        self.repl.tab()
        self.assertEqual(self.repl.s, "foo")

    @unittest.skip("disabled while non-simple completion is disabled")
    def test_substring_expand_forward(self):
        self.repl.config.autocomplete_mode = (
            autocomplete.AutocompleteModes.SUBSTRING
        )
        self.repl.s = "ba"
        self.repl.tab()
        self.assertEqual(self.repl.s, "bar")

    @unittest.skip("disabled while non-simple completion is disabled")
    def test_fuzzy_expand(self):
        pass


if __name__ == "__main__":
    unittest.main()
