import code
import os
import sys
import tempfile
import io
from typing import cast
import unittest

from contextlib import contextmanager
from functools import partial
from unittest import mock

from bpython.curtsiesfrontend import repl as curtsiesrepl
from bpython.curtsiesfrontend import interpreter
from bpython.curtsiesfrontend import events as bpythonevents
from bpython.curtsiesfrontend.repl import LineType
from bpython import autocomplete
from bpython import config
from bpython import args
from bpython.test import (
    FixLanguageTestCase as TestCase,
    MagicIterMock,
    TEST_CONFIG,
)

from curtsies import events
from curtsies.window import CursorAwareWindow
from importlib import invalidate_caches


def setup_config(conf):
    config_struct = config.Config(TEST_CONFIG)
    for key, value in conf.items():
        if not hasattr(config_struct, key):
            raise ValueError(f"{key!r} is not a valid config attribute")
        setattr(config_struct, key, value)
    return config_struct


class TestCurtsiesRepl(TestCase):
    def setUp(self):
        self.repl = create_repl()

    def cfwp(self, source):
        return interpreter.code_finished_will_parse(
            source, self.repl.interp.compile
        )

    def test_code_finished_will_parse(self):
        self.repl.buffer = ["1 + 1"]
        self.assertTrue(self.cfwp("\n".join(self.repl.buffer)), (True, True))
        self.repl.buffer = ["def foo(x):"]
        self.assertTrue(self.cfwp("\n".join(self.repl.buffer)), (False, True))
        self.repl.buffer = ["def foo(x)"]
        self.assertTrue(self.cfwp("\n".join(self.repl.buffer)), (True, False))
        self.repl.buffer = ["def foo(x):", "return 1"]
        self.assertTrue(self.cfwp("\n".join(self.repl.buffer)), (True, False))
        self.repl.buffer = ["def foo(x):", "    return 1"]
        self.assertTrue(self.cfwp("\n".join(self.repl.buffer)), (True, True))
        self.repl.buffer = ["def foo(x):", "    return 1", ""]
        self.assertTrue(self.cfwp("\n".join(self.repl.buffer)), (True, True))

    def test_external_communication(self):
        self.repl.send_current_block_to_external_editor()
        self.repl.send_session_to_external_editor()

    @unittest.skipUnless(
        all(map(config.can_encode, "å∂ßƒ")), "Charset can not encode characters"
    )
    def test_external_communication_encoding(self):
        with captured_output():
            self.repl.display_lines.append('>>> "åß∂ƒ"')
            self.repl.history.append('"åß∂ƒ"')
            self.repl.all_logical_lines.append(('"åß∂ƒ"', LineType.INPUT))
            self.repl.send_session_to_external_editor()

    def test_get_last_word(self):
        self.repl.rl_history.entries = ["1", "2 3", "4 5 6"]
        self.repl._set_current_line("abcde")
        self.repl.get_last_word()
        self.assertEqual(self.repl.current_line, "abcde6")
        self.repl.get_last_word()
        self.assertEqual(self.repl.current_line, "abcde3")

    def test_last_word(self):
        self.assertEqual(curtsiesrepl._last_word(""), "")
        self.assertEqual(curtsiesrepl._last_word(" "), "")
        self.assertEqual(curtsiesrepl._last_word("a"), "a")
        self.assertEqual(curtsiesrepl._last_word("a b"), "b")

    @unittest.skip("this is the behavior of bash - not currently implemented")
    def test_get_last_word_with_prev_line(self):
        self.repl.rl_history.entries = ["1", "2 3", "4 5 6"]
        self.repl._set_current_line("abcde")
        self.repl.up_one_line()
        self.assertEqual(self.repl.current_line, "4 5 6")
        self.repl.get_last_word()
        self.assertEqual(self.repl.current_line, "4 5 63")
        self.repl.get_last_word()
        self.assertEqual(self.repl.current_line, "4 5 64")
        self.repl.up_one_line()
        self.assertEqual(self.repl.current_line, "2 3")


def mock_next(obj, return_value):
    obj.__next__.return_value = return_value


class TestCurtsiesReplTab(TestCase):
    def setUp(self):
        self.repl = create_repl()
        self.repl.matches_iter = MagicIterMock()

        def add_matches(*args, **kwargs):
            self.repl.matches_iter.matches = ["aaa", "aab", "aac"]

        self.repl.complete = mock.Mock(
            side_effect=add_matches, return_value=True
        )

    def test_tab_with_no_matches_triggers_completion(self):
        self.repl._current_line = " asdf"
        self.repl._cursor_offset = 5
        self.repl.matches_iter.matches = []
        self.repl.matches_iter.is_cseq.return_value = False
        self.repl.matches_iter.cur_line.return_value = (None, None)
        self.repl.on_tab()
        self.repl.complete.assert_called_once_with(tab=True)

    def test_tab_after_indentation_adds_space(self):
        self.repl._current_line = "    "
        self.repl._cursor_offset = 4
        self.repl.on_tab()
        self.assertEqual(self.repl._current_line, "        ")
        self.assertEqual(self.repl._cursor_offset, 8)

    def test_tab_at_beginning_of_line_adds_space(self):
        self.repl._current_line = ""
        self.repl._cursor_offset = 0
        self.repl.on_tab()
        self.assertEqual(self.repl._current_line, "    ")
        self.assertEqual(self.repl._cursor_offset, 4)

    def test_tab_with_no_matches_selects_first(self):
        self.repl._current_line = " aa"
        self.repl._cursor_offset = 3
        self.repl.matches_iter.matches = []
        self.repl.matches_iter.is_cseq.return_value = False

        mock_next(self.repl.matches_iter, None)
        self.repl.matches_iter.cur_line.return_value = (None, None)
        self.repl.on_tab()
        self.repl.complete.assert_called_once_with(tab=True)
        self.repl.matches_iter.cur_line.assert_called_once_with()

    def test_tab_with_matches_selects_next_match(self):
        self.repl._current_line = " aa"
        self.repl._cursor_offset = 3
        self.repl.complete()
        self.repl.matches_iter.is_cseq.return_value = False
        mock_next(self.repl.matches_iter, None)
        self.repl.matches_iter.cur_line.return_value = (None, None)
        self.repl.on_tab()
        self.repl.matches_iter.cur_line.assert_called_once_with()

    def test_tab_completes_common_sequence(self):
        self.repl._current_line = " a"
        self.repl._cursor_offset = 2
        self.repl.matches_iter.matches = ["aaa", "aab", "aac"]
        self.repl.matches_iter.is_cseq.return_value = True
        self.repl.matches_iter.substitute_cseq.return_value = (None, None)
        self.repl.on_tab()
        self.repl.matches_iter.substitute_cseq.assert_called_once_with()


class TestCurtsiesReplFilenameCompletion(TestCase):
    def setUp(self):
        self.repl = create_repl()

    def test_list_win_visible_match_selected_on_tab_multiple_options(self):
        self.repl._current_line = " './'"
        self.repl._cursor_offset = 2
        with mock.patch("bpython.autocomplete.get_completer") as m:
            m.return_value = (
                ["./abc", "./abcd", "./bcd"],
                autocomplete.FilenameCompletion(),
            )
            self.repl.update_completion()
            self.assertEqual(self.repl.list_win_visible, False)
            self.repl.on_tab()
        self.assertEqual(self.repl.current_match, "./abc")
        self.assertEqual(self.repl.list_win_visible, True)

    def test_list_win_not_visible_and_cseq_if_cseq(self):
        self.repl._current_line = " './a'"
        self.repl._cursor_offset = 5
        with mock.patch("bpython.autocomplete.get_completer") as m:
            m.return_value = (
                ["./abcd", "./abce"],
                autocomplete.FilenameCompletion(),
            )
            self.repl.update_completion()
            self.assertEqual(self.repl.list_win_visible, False)
        self.repl.on_tab()
        self.assertEqual(self.repl._current_line, " './abc'")
        self.assertEqual(self.repl.current_match, None)
        self.assertEqual(self.repl.list_win_visible, False)

    def test_list_win_not_visible_and_match_selected_if_one_option(self):
        self.repl._current_line = " './a'"
        self.repl._cursor_offset = 5
        with mock.patch("bpython.autocomplete.get_completer") as m:
            m.return_value = (["./abcd"], autocomplete.FilenameCompletion())
            self.repl.update_completion()
            self.assertEqual(self.repl.list_win_visible, False)
        self.repl.on_tab()
        self.assertEqual(self.repl._current_line, " './abcd'")
        self.assertEqual(self.repl.current_match, None)
        self.assertEqual(self.repl.list_win_visible, False)


# from http://stackoverflow.com/a/17981937/398212 - thanks @rkennedy
@contextmanager
def captured_output():
    new_out, new_err = io.StringIO(), io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = new_out, new_err
        yield sys.stdout, sys.stderr
    finally:
        sys.stdout, sys.stderr = old_out, old_err


def create_repl(**kwargs):
    config = setup_config({"editor": "true"})
    repl = curtsiesrepl.BaseRepl(
        config, cast(CursorAwareWindow, None), **kwargs
    )
    os.environ["PAGER"] = "true"
    os.environ.pop("PYTHONSTARTUP", None)
    repl.width = 50
    repl.height = 20
    return repl


class TestFutureImports(TestCase):
    def test_repl(self):
        repl = create_repl()
        with captured_output() as (out, err):
            repl.push("1 / 2")
        self.assertEqual(out.getvalue(), "0.5\n")

    def test_interactive(self):
        interp = code.InteractiveInterpreter(locals={})
        with captured_output() as (out, err):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py") as f:
                f.write("print(1/2)\n")
                f.flush()
                args.exec_code(interp, [f.name])

            repl = create_repl(interp=interp)
            repl.push("1 / 2")

        self.assertEqual(out.getvalue(), "0.5\n0.5\n")


class TestStdOutErr(TestCase):
    def setUp(self):
        self.repl = create_repl()

    def test_newline(self):
        self.repl.send_to_stdouterr("\n\n")
        self.assertEqual(self.repl.display_lines[-2], "")
        self.assertEqual(self.repl.display_lines[-1], "")
        self.assertEqual(self.repl.current_stdouterr_line, "")

    def test_leading_newline(self):
        self.repl.send_to_stdouterr("\nfoo\n")
        self.assertEqual(self.repl.display_lines[-2], "")
        self.assertEqual(self.repl.display_lines[-1], "foo")
        self.assertEqual(self.repl.current_stdouterr_line, "")

    def test_no_trailing_newline(self):
        self.repl.send_to_stdouterr("foo")
        self.assertEqual(self.repl.current_stdouterr_line, "foo")

    def test_print_without_newline_then_print_with_leading_newline(self):
        self.repl.send_to_stdouterr("foo")
        self.repl.send_to_stdouterr("\nbar\n")
        self.assertEqual(self.repl.display_lines[-2], "foo")
        self.assertEqual(self.repl.display_lines[-1], "bar")
        self.assertEqual(self.repl.current_stdouterr_line, "")


class TestPredictedIndent(TestCase):
    def setUp(self):
        self.repl = create_repl()

    def test_simple(self):
        self.assertEqual(self.repl.predicted_indent(""), 0)
        self.assertEqual(self.repl.predicted_indent("class Foo:"), 4)
        self.assertEqual(self.repl.predicted_indent("class Foo: pass"), 0)
        self.assertEqual(self.repl.predicted_indent("def asdf():"), 4)
        self.assertEqual(self.repl.predicted_indent("def asdf(): return 7"), 0)

    @unittest.skip("This would be interesting")
    def test_complex(self):
        self.assertEqual(self.repl.predicted_indent("[a, "), 1)
        self.assertEqual(self.repl.predicted_indent("reduce(asdfasdf, "), 7)


class TestCurtsiesReevaluate(TestCase):
    def setUp(self):
        self.repl = create_repl()

    def test_variable_is_cleared(self):
        self.repl._current_line = "b = 10"
        self.repl.on_enter()
        self.assertIn("b", self.repl.interp.locals)
        self.repl.undo()
        self.assertNotIn("b", self.repl.interp.locals)


class TestCurtsiesReevaluateWithImport(TestCase):
    def setUp(self):
        self.repl = create_repl()
        self.open = partial(io.open, mode="wt", encoding="utf-8")
        self.dont_write_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        self.sys_path = sys.path
        sys.path = self.sys_path[:]

        # Because these tests create Python source files at runtime,
        # it's possible in Python >=3.3 for the importlib.machinery.FileFinder
        # for a directory to have an outdated cache when
        # * a module in that directory is imported,
        # * then a new module is created in that directory,
        # * then that new module is imported.
        # Automatic cache invalidation is based on the second-resolution mtime
        # of the directory, so we need to manually call invalidate_caches().
        #
        # see https://docs.python.org/3/library/importlib.html
        # sections #importlib.machinery.FileFinder and
        # #importlib.invalidate_caches
        invalidate_caches()

    def tearDown(self):
        sys.dont_write_bytecode = self.dont_write_bytecode
        sys.path = self.sys_path

    def push(self, line):
        self.repl._current_line = line
        self.repl.on_enter()

    def head(self, path):
        self.push("import sys")
        self.push('sys.path.append("%s")' % (path))

    @staticmethod
    @contextmanager
    def tempfile():
        with tempfile.NamedTemporaryFile(suffix=".py") as temp:
            path, name = os.path.split(temp.name)
            yield temp.name, path, name.replace(".py", "")

    def test_module_content_changed(self):
        with self.tempfile() as (fullpath, path, modname):
            print(modname)
            with self.open(fullpath) as f:
                f.write("a = 0\n")
            self.head(path)
            self.push("import %s" % (modname))
            self.push("a = %s.a" % (modname))
            self.assertIn("a", self.repl.interp.locals)
            self.assertEqual(self.repl.interp.locals["a"], 0)
            with self.open(fullpath) as f:
                f.write("a = 1\n")
            self.repl.clear_modules_and_reevaluate()
            self.assertIn("a", self.repl.interp.locals)
            self.assertEqual(self.repl.interp.locals["a"], 1)

    def test_import_module_with_rewind(self):
        with self.tempfile() as (fullpath, path, modname):
            print(modname)
            with self.open(fullpath) as f:
                f.write("a = 0\n")
            self.head(path)
            self.push("import %s" % (modname))
            self.assertIn(modname, self.repl.interp.locals)
            self.repl.undo()
            self.assertNotIn(modname, self.repl.interp.locals)
            self.repl.clear_modules_and_reevaluate()
            self.assertNotIn(modname, self.repl.interp.locals)
            self.push("import %s" % (modname))
            self.push("a = %s.a" % (modname))
            self.assertIn("a", self.repl.interp.locals)
            self.assertEqual(self.repl.interp.locals["a"], 0)
            with self.open(fullpath) as f:
                f.write("a = 1\n")
            self.repl.clear_modules_and_reevaluate()
            self.assertIn("a", self.repl.interp.locals)
            self.assertEqual(self.repl.interp.locals["a"], 1)


class TestCurtsiesPagerText(TestCase):
    def setUp(self):
        self.repl = create_repl()
        self.repl.pager = self.assert_pager_gets_unicode

    def assert_pager_gets_unicode(self, text):
        self.assertIsInstance(text, str)

    def test_help(self):
        self.repl.pager(self.repl.help_text())

    @unittest.skipUnless(
        all(map(config.can_encode, "å∂ßƒ")), "Charset can not encode characters"
    )
    def test_show_source_not_formatted(self):
        self.repl.config.highlight_show_source = False
        self.repl.get_source_of_current_name = lambda: "source code å∂ßƒåß∂ƒ"
        self.repl.show_source()

    @unittest.skipUnless(
        all(map(config.can_encode, "å∂ßƒ")), "Charset can not encode characters"
    )
    def test_show_source_formatted(self):
        self.repl.config.highlight_show_source = True
        self.repl.get_source_of_current_name = lambda: "source code å∂ßƒåß∂ƒ"
        self.repl.show_source()


class TestCurtsiesStartup(TestCase):
    def setUp(self):
        self.repl = create_repl()

    def write_startup_file(self, fname, encoding):
        with open(fname, mode="wt", encoding=encoding) as f:
            f.write("# coding: ")
            f.write(encoding)
            f.write("\n")
            f.write('a = "äöü"\n')

    def test_startup_event_utf8(self):
        with tempfile.NamedTemporaryFile() as temp:
            self.write_startup_file(temp.name, "utf-8")
            with mock.patch.dict("os.environ", {"PYTHONSTARTUP": temp.name}):
                self.repl.process_event(bpythonevents.RunStartupFileEvent())
        self.assertIn("a", self.repl.interp.locals)

    def test_startup_event_latin1(self):
        with tempfile.NamedTemporaryFile() as temp:
            self.write_startup_file(temp.name, "latin-1")
            with mock.patch.dict("os.environ", {"PYTHONSTARTUP": temp.name}):
                self.repl.process_event(bpythonevents.RunStartupFileEvent())
        self.assertIn("a", self.repl.interp.locals)


class TestCurtsiesPasteEvents(TestCase):
    def setUp(self):
        self.repl = create_repl()

    def test_control_events_in_small_paste(self):
        self.assertGreaterEqual(
            curtsiesrepl.MAX_EVENTS_POSSIBLY_NOT_PASTE,
            6,
            "test assumes UI lag could cause 6 events",
        )
        p = events.PasteEvent()
        p.events = ["a", "b", "c", "d", "<Ctrl-a>", "e"]
        self.repl.process_event(p)
        self.assertEqual(self.repl.current_line, "eabcd")

    def test_control_events_in_large_paste(self):
        """Large paste events should ignore control characters"""
        p = events.PasteEvent()
        p.events = ["a", "<Ctrl-a>"] + [
            "e"
        ] * curtsiesrepl.MAX_EVENTS_POSSIBLY_NOT_PASTE
        self.repl.process_event(p)
        self.assertEqual(
            self.repl.current_line,
            "a" + "e" * curtsiesrepl.MAX_EVENTS_POSSIBLY_NOT_PASTE,
        )


if __name__ == "__main__":
    unittest.main()
