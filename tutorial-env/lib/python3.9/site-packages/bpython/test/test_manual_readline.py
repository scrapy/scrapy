import unittest

from bpython.curtsiesfrontend.manual_readline import (
    left_arrow,
    right_arrow,
    beginning_of_line,
    forward_word,
    back_word,
    end_of_line,
    delete,
    last_word_pos,
    backspace,
    delete_from_cursor_back,
    delete_from_cursor_forward,
    delete_rest_of_word,
    delete_word_to_cursor,
    transpose_character_before_cursor,
    UnconfiguredEdits,
    delete_word_from_cursor_back,
)


class TestManualReadline(unittest.TestCase):
    def setUp(self):
        self._line = "this is my test string"

    def tearDown(self):
        pass

    def test_left_arrow_at_zero(self):
        pos = 0
        expected = (pos, self._line)
        result = left_arrow(pos, self._line)
        self.assertEqual(expected, result)

    def test_left_arrow_at_non_zero(self):
        for i in range(1, len(self._line)):
            expected = (i - 1, self._line)
            result = left_arrow(i, self._line)
            self.assertEqual(expected, result)

    def test_right_arrow_at_end(self):
        pos = len(self._line)
        expected = (pos, self._line)
        result = right_arrow(pos, self._line)
        self.assertEqual(expected, result)

    def test_right_arrow_at_non_end(self):
        for i in range(len(self._line) - 1):
            expected = (i + 1, self._line)
            result = right_arrow(i, self._line)
            self.assertEqual(expected, result)

    def test_beginning_of_line(self):
        expected = (0, self._line)
        for i in range(len(self._line)):
            result = beginning_of_line(i, self._line)
            self.assertEqual(expected, result)

    def test_end_of_line(self):
        expected = (len(self._line), self._line)
        for i in range(len(self._line)):
            result = end_of_line(i, self._line)
            self.assertEqual(expected, result)

    def test_forward_word(self):
        line = "going from here to_here"
        start_pos = 11
        next_word_pos = 15
        expected = (next_word_pos, line)
        result = forward_word(start_pos, line)
        self.assertEqual(expected, result)
        start_pos = 15
        next_word_pos = 23
        expected = (next_word_pos, line)
        result = forward_word(start_pos, line)
        self.assertEqual(expected, result)

    def test_forward_word_tabs(self):
        line = "going from here      to_here"
        start_pos = 11
        next_word_pos = 15
        expected = (next_word_pos, line)
        result = forward_word(start_pos, line)
        self.assertEqual(expected, result)
        start_pos = 15
        next_word_pos = 28
        expected = (next_word_pos, line)
        result = forward_word(start_pos, line)
        self.assertEqual(expected, result)

    def test_forward_word_end(self):
        line = "going from here to_here"
        start_pos = 16
        next_word_pos = 23
        expected = (next_word_pos, line)
        result = forward_word(start_pos, line)
        self.assertEqual(expected, result)
        start_pos = 22
        next_word_pos = 23
        expected = (next_word_pos, line)
        result = forward_word(start_pos, line)
        self.assertEqual(expected, result)
        start_pos = 23
        next_word_pos = 23
        expected = (next_word_pos, line)
        result = forward_word(start_pos, line)
        self.assertEqual(expected, result)

    def test_forward_word_empty(self):
        line = ""
        start_pos = 0
        next_word_pos = 0
        expected = (next_word_pos, line)
        result = forward_word(start_pos, line)
        self.assertEqual(expected, result)

    def test_back_word(self):
        line = "going to here from_here"
        start_pos = 14
        prev_word_pos = 9
        self.assertEqual(line[start_pos], "f")
        self.assertEqual(line[prev_word_pos], "h")
        expected = (prev_word_pos, line)
        result = back_word(start_pos, line)
        self.assertEqual(expected, result)

    def test_last_word_pos(self):
        line = "a word"
        expected = 2
        result = last_word_pos(line)
        self.assertEqual(expected, result)

    def test_last_word_pos_single_word(self):
        line = "word"
        expected = 0
        result = last_word_pos(line)
        self.assertEqual(expected, result)

    def test_delete(self):
        line = "deletion line"
        pos = 3
        expected = (3, "deltion line")
        result = delete(pos, line)
        self.assertEqual(expected, result)

    def test_delete_from_cursor_back(self):
        line = "everything before this will be deleted"
        expected = (0, "this will be deleted")
        result = delete_from_cursor_back(line.find("this"), line)
        self.assertEqual(expected, result)

    def test_delete_from_cursor_forward(self):
        line = "everything after this will be deleted"
        pos = line.find("this")
        expected = (pos, "everything after ")
        result = delete_from_cursor_forward(line.find("this"), line)[:-1]
        self.assertEqual(expected, result)
        self.assertEqual(delete_from_cursor_forward(0, ""), (0, "", ""))

    def test_delete_rest_of_word(self):
        self.try_stages_kill(
            [
                "z|s;df asdf d s;a;a",
                "z|;df asdf d s;a;a",
                "z| asdf d s;a;a",
                "z| d s;a;a",
                "z| s;a;a",
                "z|;a;a",
                "z|;a",
                "z|",
                "z|",
            ],
            delete_rest_of_word,
        )

    def test_delete_word_to_cursor(self):
        self.try_stages_kill(
            [
                "  a;d sdf ;a;s;d; fjksald|a",
                "  a;d sdf ;a;s;d; |a",
                "  a;d sdf |a",
                "  a;d |a",
                "  |a",
                "|a",
                "|a",
            ],
            delete_word_to_cursor,
        )

    def test_yank_prev_killed_text(self):
        pass

    def test_yank_prev_prev_killed_text(self):
        pass

    def try_stages(self, strings, func):
        if not all("|" in s for s in strings):
            raise ValueError("Need to use '|' to specify cursor")

        stages = [(s.index("|"), s.replace("|", "")) for s in strings]
        for (initial_pos, initial), (final_pos, final) in zip(
            stages[:-1], stages[1:]
        ):
            self.assertEqual(func(initial_pos, initial), (final_pos, final))

    def try_stages_kill(self, strings, func):
        if not all("|" in s for s in strings):
            raise ValueError("Need to use '|' to specify cursor")

        stages = [(s.index("|"), s.replace("|", "")) for s in strings]
        for (initial_pos, initial), (final_pos, final) in zip(
            stages[:-1], stages[1:]
        ):
            self.assertEqual(
                func(initial_pos, initial)[:-1], (final_pos, final)
            )

    def test_transpose_character_before_cursor(self):
        self.try_stages(
            [
                "as|df asdf",
                "ads|f asdf",
                "adfs| asdf",
                "adf s|asdf",
                "adf as|sdf",
            ],
            transpose_character_before_cursor,
        )

    def test_transpose_empty_line(self):
        self.assertEqual(transpose_character_before_cursor(0, ""), (0, ""))

    def test_transpose_first_character(self):
        self.assertEqual(transpose_character_before_cursor(0, "a"), (0, "a"))
        self.assertEqual(transpose_character_before_cursor(0, "as"), (0, "as"))

    def test_transpose_end_of_line(self):
        self.assertEqual(transpose_character_before_cursor(1, "a"), (1, "a"))
        self.assertEqual(transpose_character_before_cursor(2, "as"), (2, "sa"))

    def test_transpose_word_before_cursor(self):
        pass

    def test_backspace(self):
        self.assertEqual(backspace(2, "as"), (1, "a"))
        self.assertEqual(backspace(3, "as "), (2, "as"))

    def test_delete_word_from_cursor_back(self):
        self.try_stages_kill(
            [
                "asd;fljk asd;lfjas;dlkfj asdlk jasdf;ljk|",
                "asd;fljk asd;lfjas;dlkfj asdlk jasdf;|",
                "asd;fljk asd;lfjas;dlkfj asdlk |",
                "asd;fljk asd;lfjas;dlkfj |",
                "asd;fljk asd;lfjas;|",
                "asd;fljk asd;|",
                "asd;fljk |",
                "asd;|",
                "|",
                "|",
            ],
            delete_word_from_cursor_back,
        )

        self.try_stages_kill(
            [" (( asdf |", " (( |", "|"], delete_word_from_cursor_back
        )


class TestEdits(unittest.TestCase):
    def setUp(self):
        self.edits = UnconfiguredEdits()

    def test_seq(self):
        def f(cursor_offset, line):
            return ("hi", 2)

        self.edits.add("a", f)
        self.assertIn("a", self.edits)
        self.assertEqual(self.edits["a"], f)
        self.assertEqual(
            self.edits.call("a", cursor_offset=3, line="hello"), ("hi", 2)
        )
        with self.assertRaises(KeyError):
            self.edits["b"]
        with self.assertRaises(KeyError):
            self.edits.call("b")

    def test_functions_with_bad_signatures(self):
        def f(something):
            return (1, 2)

        with self.assertRaises(TypeError):
            self.edits.add("a", f)

        def g(cursor_offset, line, something, something_else):
            return (1, 2)

        with self.assertRaises(TypeError):
            self.edits.add("a", g)

    def test_functions_with_bad_return_values(self):
        def f(cursor_offset, line):
            return ("hi",)

        with self.assertRaises(ValueError):
            self.edits.add("a", f)

        def g(cursor_offset, line):
            return ("hi", 1, 2, 3)

        with self.assertRaises(ValueError):
            self.edits.add("b", g)

    def test_config(self):
        def f(cursor_offset, line):
            return ("hi", 2)

        def g(cursor_offset, line):
            return ("hey", 3)

        self.edits.add_config_attr("att", f)
        self.assertNotIn("att", self.edits)

        class config:
            att = "c"

        key_dispatch = {"c": "c"}
        configured_edits = self.edits.mapping_with_config(config, key_dispatch)
        self.assertTrue(configured_edits.__contains__, "c")
        self.assertNotIn("c", self.edits)
        with self.assertRaises(NotImplementedError):
            configured_edits.add_config_attr("att2", g)
        with self.assertRaises(NotImplementedError):
            configured_edits.add("d", g)
        self.assertEqual(
            configured_edits.call("c", cursor_offset=5, line="asfd"), ("hi", 2)
        )


if __name__ == "__main__":
    unittest.main()
