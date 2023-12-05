import os
from typing import cast

from bpython.test import FixLanguageTestCase as TestCase, TEST_CONFIG
from bpython.curtsiesfrontend import repl as curtsiesrepl
from bpython import config

from curtsies.window import CursorAwareWindow


def setup_config(conf):
    config_struct = config.Config(TEST_CONFIG)
    for key, value in conf.items():
        if not hasattr(config_struct, key):
            raise ValueError(f"{key!r} is not a valid config attribute")
        setattr(config_struct, key, value)
    return config_struct


def create_repl(brackets_enabled=False, **kwargs):
    config = setup_config(
        {"editor": "true", "brackets_completion": brackets_enabled}
    )
    repl = curtsiesrepl.BaseRepl(
        config, cast(CursorAwareWindow, None), **kwargs
    )
    os.environ["PAGER"] = "true"
    os.environ.pop("PYTHONSTARTUP", None)
    repl.width = 50
    repl.height = 20
    return repl


class TestBracketCompletionEnabled(TestCase):
    def setUp(self):
        self.repl = create_repl(brackets_enabled=True)

    def process_multiple_events(self, event_list):
        for event in event_list:
            self.repl.process_event(event)

    def test_start_line(self):
        self.repl.process_event("(")
        self.assertEqual(self.repl._current_line, "()")
        self.assertEqual(self.repl._cursor_offset, 1)

    def test_nested_brackets(self):
        self.process_multiple_events(["(", "[", "{"])
        self.assertEqual(self.repl._current_line, """([{}])""")
        self.assertEqual(self.repl._cursor_offset, 3)

    def test_quotes(self):
        self.process_multiple_events(["(", "'", "x", "<TAB>", ","])
        self.process_multiple_events(["[", '"', "y", "<TAB>", "<TAB>", "<TAB>"])
        self.assertEqual(self.repl._current_line, """('x',["y"])""")
        self.assertEqual(self.repl._cursor_offset, 11)

    def test_bracket_overwrite_closing_char(self):
        self.process_multiple_events(["(", "[", "{"])
        self.assertEqual(self.repl._current_line, """([{}])""")
        self.assertEqual(self.repl._cursor_offset, 3)
        self.process_multiple_events(["}", "]", ")"])
        self.assertEqual(self.repl._current_line, """([{}])""")
        self.assertEqual(self.repl._cursor_offset, 6)

    def test_brackets_move_cursor_on_tab(self):
        self.process_multiple_events(["(", "[", "{"])
        self.assertEqual(self.repl._current_line, """([{}])""")
        self.assertEqual(self.repl._cursor_offset, 3)
        self.repl.process_event("<TAB>")
        self.assertEqual(self.repl._current_line, """([{}])""")
        self.assertEqual(self.repl._cursor_offset, 4)
        self.repl.process_event("<TAB>")
        self.assertEqual(self.repl._current_line, """([{}])""")
        self.assertEqual(self.repl._cursor_offset, 5)
        self.repl.process_event("<TAB>")
        self.assertEqual(self.repl._current_line, """([{}])""")
        self.assertEqual(self.repl._cursor_offset, 6)

    def test_brackets_non_whitespace_following_char(self):
        self.repl.current_line = "s = s.connect('localhost', 8080)"
        self.repl.cursor_offset = 14
        self.repl.process_event("(")
        self.assertEqual(
            self.repl._current_line, "s = s.connect(('localhost', 8080)"
        )
        self.assertEqual(self.repl._cursor_offset, 15)

    def test_brackets_deletion_on_backspace(self):
        self.repl.current_line = "def foo()"
        self.repl.cursor_offset = 8
        self.repl.process_event("<BACKSPACE>")
        self.assertEqual(self.repl._current_line, "def foo")
        self.assertEqual(self.repl.cursor_offset, 7)

    def test_brackets_deletion_on_backspace_nested(self):
        self.repl.current_line = '([{""}])'
        self.repl.cursor_offset = 4
        self.process_multiple_events(
            ["<BACKSPACE>", "<BACKSPACE>", "<BACKSPACE>"]
        )
        self.assertEqual(self.repl._current_line, "()")
        self.assertEqual(self.repl.cursor_offset, 1)


class TestBracketCompletionDisabled(TestCase):
    def setUp(self):
        self.repl = create_repl(brackets_enabled=False)

    def process_multiple_events(self, event_list):
        for event in event_list:
            self.repl.process_event(event)

    def test_start_line(self):
        self.repl.process_event("(")
        self.assertEqual(self.repl._current_line, "(")
        self.assertEqual(self.repl._cursor_offset, 1)

    def test_nested_brackets(self):
        self.process_multiple_events(["(", "[", "{"])
        self.assertEqual(self.repl._current_line, "([{")
        self.assertEqual(self.repl._cursor_offset, 3)

    def test_bracket_overwrite_closing_char(self):
        self.process_multiple_events(["(", "[", "{"])
        self.assertEqual(self.repl._current_line, """([{""")
        self.assertEqual(self.repl._cursor_offset, 3)
        self.process_multiple_events(["}", "]", ")"])
        self.assertEqual(self.repl._current_line, """([{}])""")
        self.assertEqual(self.repl._cursor_offset, 6)

    def test_brackets_move_cursor_on_tab(self):
        self.process_multiple_events(["(", "[", "{"])
        self.assertEqual(self.repl._current_line, """([{""")
        self.assertEqual(self.repl._cursor_offset, 3)
        self.repl.process_event("<TAB>")
        self.assertEqual(self.repl._current_line, """([{""")
        self.assertEqual(self.repl._cursor_offset, 3)

    def test_brackets_deletion_on_backspace(self):
        self.repl.current_line = "def foo()"
        self.repl.cursor_offset = 8
        self.repl.process_event("<BACKSPACE>")
        self.assertEqual(self.repl._current_line, "def foo")
        self.assertEqual(self.repl.cursor_offset, 7)

    def test_brackets_deletion_on_backspace_nested(self):
        self.repl.current_line = '([{""}])'
        self.repl.cursor_offset = 4
        self.process_multiple_events(
            ["<BACKSPACE>", "<BACKSPACE>", "<BACKSPACE>"]
        )
        self.assertEqual(self.repl._current_line, "()")
        self.assertEqual(self.repl.cursor_offset, 1)
