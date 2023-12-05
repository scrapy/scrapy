import inspect
import keyword
import unittest
from collections import namedtuple
from unittest import mock

try:
    import jedi

    has_jedi = True
except ImportError:
    has_jedi = False

from bpython import autocomplete, inspection
from bpython.line import LinePart

glob_function = "glob.iglob"


class TestSafeEval(unittest.TestCase):
    def test_catches_syntax_error(self):
        with self.assertRaises(autocomplete.EvaluationError):
            autocomplete.safe_eval("1re", {})


class TestFormatters(unittest.TestCase):
    def test_filename(self):
        completer = autocomplete.FilenameCompletion()
        last_part_of_filename = completer.format
        self.assertEqual(last_part_of_filename("abc"), "abc")
        self.assertEqual(last_part_of_filename("abc/"), "abc/")
        self.assertEqual(last_part_of_filename("abc/efg"), "efg")
        self.assertEqual(last_part_of_filename("abc/efg/"), "efg/")
        self.assertEqual(last_part_of_filename("/abc"), "abc")
        self.assertEqual(last_part_of_filename("ab.c/e.f.g/"), "e.f.g/")

    def test_attribute(self):
        self.assertEqual(autocomplete._after_last_dot("abc.edf"), "edf")


def completer(matches):
    mock_completer = autocomplete.BaseCompletionType()
    mock_completer.matches = mock.Mock(return_value=matches)
    return mock_completer


class TestGetCompleter(unittest.TestCase):
    def test_no_completers(self):
        self.assertTupleEqual(autocomplete.get_completer([], 0, ""), ([], None))

    def test_one_completer_without_matches_returns_empty_list_and_none(self):
        a = completer([])
        self.assertTupleEqual(
            autocomplete.get_completer([a], 0, ""), ([], None)
        )

    def test_one_completer_returns_matches_and_completer(self):
        a = completer(["a"])
        self.assertTupleEqual(
            autocomplete.get_completer([a], 0, ""), (["a"], a)
        )

    def test_two_completers_with_matches_returns_first_matches(self):
        a = completer(["a"])
        b = completer(["b"])
        self.assertEqual(autocomplete.get_completer([a, b], 0, ""), (["a"], a))

    def test_first_non_none_completer_matches_are_returned(self):
        a = completer([])
        b = completer(["a"])
        self.assertEqual(autocomplete.get_completer([a, b], 0, ""), ([], None))

    def test_only_completer_returns_None(self):
        a = completer(None)
        self.assertEqual(autocomplete.get_completer([a], 0, ""), ([], None))

    def test_first_completer_returns_None(self):
        a = completer(None)
        b = completer(["a"])
        self.assertEqual(autocomplete.get_completer([a, b], 0, ""), (["a"], b))


class TestCumulativeCompleter(unittest.TestCase):
    def completer(self, matches):
        mock_completer = autocomplete.BaseCompletionType()
        mock_completer.matches = mock.Mock(return_value=matches)
        return mock_completer

    def test_no_completers_fails(self):
        with self.assertRaises(ValueError):
            autocomplete.CumulativeCompleter([])

    def test_one_empty_completer_returns_empty(self):
        a = self.completer([])
        cumulative = autocomplete.CumulativeCompleter([a])
        self.assertEqual(cumulative.matches(3, "abc"), set())

    def test_one_none_completer_returns_none(self):
        a = self.completer(None)
        cumulative = autocomplete.CumulativeCompleter([a])
        self.assertEqual(cumulative.matches(3, "abc"), None)

    def test_two_completers_get_both(self):
        a = self.completer(["a"])
        b = self.completer(["b"])
        cumulative = autocomplete.CumulativeCompleter([a, b])
        self.assertEqual(cumulative.matches(3, "abc"), {"a", "b"})


class TestFilenameCompletion(unittest.TestCase):
    def setUp(self):
        self.completer = autocomplete.FilenameCompletion()

    def test_locate_fails_when_not_in_string(self):
        self.assertEqual(self.completer.locate(4, "abcd"), None)

    def test_locate_succeeds_when_in_string(self):
        self.assertEqual(
            self.completer.locate(4, "a'bc'd"), LinePart(2, 4, "bc")
        )

    def test_issue_491(self):
        self.assertNotEqual(self.completer.matches(9, '"a[a.l-1]'), None)

    @mock.patch(glob_function, new=lambda text: [])
    def test_match_returns_none_if_not_in_string(self):
        self.assertEqual(self.completer.matches(2, "abcd"), None)

    @mock.patch(glob_function, new=lambda text: [])
    def test_match_returns_empty_list_when_no_files(self):
        self.assertEqual(self.completer.matches(2, '"a'), set())

    @mock.patch(glob_function, new=lambda text: ["abcde", "aaaaa"])
    @mock.patch("os.path.expanduser", new=lambda text: text)
    @mock.patch("os.path.isdir", new=lambda text: False)
    @mock.patch("os.path.sep", new="/")
    def test_match_returns_files_when_files_exist(self):
        self.assertEqual(
            sorted(self.completer.matches(2, '"x')), ["aaaaa", "abcde"]
        )

    @mock.patch(glob_function, new=lambda text: ["abcde", "aaaaa"])
    @mock.patch("os.path.expanduser", new=lambda text: text)
    @mock.patch("os.path.isdir", new=lambda text: True)
    @mock.patch("os.path.sep", new="/")
    def test_match_returns_dirs_when_dirs_exist(self):
        self.assertEqual(
            sorted(self.completer.matches(2, '"x')), ["aaaaa/", "abcde/"]
        )

    @mock.patch(
        glob_function, new=lambda text: ["/expand/ed/abcde", "/expand/ed/aaaaa"]
    )
    @mock.patch(
        "os.path.expanduser", new=lambda text: text.replace("~", "/expand/ed")
    )
    @mock.patch("os.path.isdir", new=lambda text: False)
    @mock.patch("os.path.sep", new="/")
    def test_tilde_stays_pretty(self):
        self.assertEqual(
            sorted(self.completer.matches(4, '"~/a')), ["~/aaaaa", "~/abcde"]
        )

    @mock.patch("os.path.sep", new="/")
    def test_formatting_takes_just_last_part(self):
        self.assertEqual(self.completer.format("/hello/there/"), "there/")
        self.assertEqual(self.completer.format("/hello/there"), "there")


class MockNumPy:
    """This is a mock numpy object that raises an error when there is an attempt
    to convert it to a boolean."""

    def __nonzero__(self):
        raise ValueError(
            "The truth value of an array with more than one "
            "element is ambiguous. Use a.any() or a.all()"
        )


class TestDictKeyCompletion(unittest.TestCase):
    def test_set_of_keys_returned_when_matches_found(self):
        com = autocomplete.DictKeyCompletion()
        local = {"d": {"ab": 1, "cd": 2}}
        self.assertSetEqual(
            com.matches(2, "d[", locals_=local), {"'ab']", "'cd']"}
        )

    def test_none_returned_when_eval_error(self):
        com = autocomplete.DictKeyCompletion()
        local = {"e": {"ab": 1, "cd": 2}}
        self.assertEqual(com.matches(2, "d[", locals_=local), None)

    def test_none_returned_when_not_dict_type(self):
        com = autocomplete.DictKeyCompletion()
        local = {"l": ["ab", "cd"]}
        self.assertEqual(com.matches(2, "l[", locals_=local), None)

    def test_none_returned_when_no_matches_left(self):
        com = autocomplete.DictKeyCompletion()
        local = {"d": {"ab": 1, "cd": 2}}
        self.assertEqual(com.matches(3, "d[r", locals_=local), None)

    def test_obj_that_does_not_allow_conversion_to_bool(self):
        com = autocomplete.DictKeyCompletion()
        local = {"mNumPy": MockNumPy()}
        self.assertEqual(com.matches(7, "mNumPy[", locals_=local), None)


class Foo:
    a = 10

    def __init__(self):
        self.b = 20

    def method(self, x):
        pass


class Properties(Foo):
    @property
    def asserts_when_called(self):
        raise AssertionError("getter method called")


class Slots:
    __slots__ = ["a", "b"]


class OverriddenGetattribute(Foo):
    def __getattribute__(self, name):
        raise AssertionError("custom get attribute invoked")


class TestAttrCompletion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.com = autocomplete.AttrCompletion()

    def test_att_matches_found_on_instance(self):
        self.assertSetEqual(
            self.com.matches(2, "a.", locals_={"a": Foo()}),
            {"a.method", "a.a", "a.b"},
        )

    def test_descriptor_attributes_not_run(self):
        com = autocomplete.AttrCompletion()
        self.assertSetEqual(
            com.matches(2, "a.", locals_={"a": Properties()}),
            {"a.b", "a.a", "a.method", "a.asserts_when_called"},
        )

    def test_custom_get_attribute_not_invoked(self):
        com = autocomplete.AttrCompletion()
        self.assertSetEqual(
            com.matches(2, "a.", locals_={"a": OverriddenGetattribute()}),
            {"a.b", "a.a", "a.method"},
        )

    def test_slots_not_crash(self):
        com = autocomplete.AttrCompletion()
        self.assertSetEqual(
            com.matches(2, "A.", locals_={"A": Slots}),
            {"A.b", "A.a"},
        )


class TestExpressionAttributeCompletion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.com = autocomplete.ExpressionAttributeCompletion()

    def test_att_matches_found_on_instance(self):
        self.assertSetEqual(
            self.com.matches(5, "a[0].", locals_={"a": [Foo()]}),
            {"method", "a", "b"},
        )

    def test_other_getitem_methods_not_called(self):
        class FakeList:
            def __getitem__(inner_self, i):
                self.fail("possibly side-effecting __getitem_ method called")

        self.com.matches(5, "a[0].", locals_={"a": FakeList()})

    def test_tuples_complete(self):
        self.assertSetEqual(
            self.com.matches(5, "a[0].", locals_={"a": (Foo(),)}),
            {"method", "a", "b"},
        )

    @unittest.skip("TODO, subclasses do not complete yet")
    def test_list_subclasses_complete(self):
        class ListSubclass(list):
            pass

        self.assertSetEqual(
            self.com.matches(5, "a[0].", locals_={"a": ListSubclass([Foo()])}),
            {"method", "a", "b"},
        )

    def test_getitem_not_called_in_list_subclasses_overriding_getitem(self):
        class FakeList(list):
            def __getitem__(inner_self, i):
                self.fail("possibly side-effecting __getitem_ method called")

        self.com.matches(5, "a[0].", locals_={"a": FakeList()})

    def test_literals_complete(self):
        self.assertSetEqual(
            self.com.matches(10, "[a][0][0].", locals_={"a": (Foo(),)}),
            {"method", "a", "b"},
        )

    def test_dictionaries_complete(self):
        self.assertSetEqual(
            self.com.matches(7, 'a["b"].', locals_={"a": {"b": Foo()}}),
            {"method", "a", "b"},
        )


class TestMagicMethodCompletion(unittest.TestCase):
    def test_magic_methods_complete_after_double_underscores(self):
        com = autocomplete.MagicMethodCompletion()
        block = "class Something(object)\n    def __"
        self.assertSetEqual(
            com.matches(
                10,
                "    def __",
                current_block=block,
                complete_magic_methods=True,
            ),
            set(autocomplete.MAGIC_METHODS),
        )


Completion = namedtuple("Completion", ["name", "complete"])


@unittest.skipUnless(has_jedi, "jedi required")
class TestMultilineJediCompletion(unittest.TestCase):
    def test_returns_none_with_single_line(self):
        com = autocomplete.MultilineJediCompletion()
        self.assertEqual(
            com.matches(2, "Va", current_block="Va", history=[]), None
        )

    def test_returns_non_with_blank_second_line(self):
        com = autocomplete.MultilineJediCompletion()
        self.assertEqual(
            com.matches(
                0, "", current_block="class Foo():\n", history=["class Foo():"]
            ),
            None,
        )

    def matches_from_completions(
        self, cursor, line, block, history, completions
    ):
        with mock.patch("bpython.autocomplete.jedi.Script") as Script:
            script = Script.return_value
            script.complete.return_value = completions
            com = autocomplete.MultilineJediCompletion()
            return com.matches(
                cursor, line, current_block=block, history=history
            )

    def test_completions_starting_with_different_letters(self):
        matches = self.matches_from_completions(
            2,
            " a",
            "class Foo:\n a",
            ["adsf"],
            [Completion("Abc", "bc"), Completion("Cbc", "bc")],
        )
        self.assertEqual(matches, None)

    def test_completions_starting_with_different_cases(self):
        matches = self.matches_from_completions(
            2,
            " a",
            "class Foo:\n a",
            ["adsf"],
            [Completion("Abc", "bc"), Completion("ade", "de")],
        )
        self.assertSetEqual(matches, {"ade"})

    def test_issue_544(self):
        com = autocomplete.MultilineJediCompletion()
        code = "@asyncio.coroutine\ndef"
        history = ("import asyncio", "@asyncio.coroutin")
        com.matches(3, "def", current_block=code, history=history)


class TestGlobalCompletion(unittest.TestCase):
    def setUp(self):
        self.com = autocomplete.GlobalCompletion()

    def test_function(self):
        def function():
            pass

        self.assertEqual(
            self.com.matches(8, "function", locals_={"function": function}),
            {"function("},
        )

    def test_completions_are_unicode(self):
        for m in self.com.matches(1, "a", locals_={"abc": 10}):
            self.assertIsInstance(m, str)

    def test_mock_kwlist(self):
        with mock.patch.object(keyword, "kwlist", new=["abcd"]):
            self.assertEqual(self.com.matches(3, "abc", locals_={}), None)

    def test_mock_kwlist_non_ascii(self):
        with mock.patch.object(keyword, "kwlist", new=["abcß"]):
            self.assertEqual(self.com.matches(3, "abc", locals_={}), None)


class TestParameterNameCompletion(unittest.TestCase):
    def test_set_of_params_returns_when_matches_found(self):
        def func(apple, apricot, banana, carrot):
            pass

        argspec = inspection.ArgSpec(*inspect.getfullargspec(func))
        funcspec = inspection.FuncProps("func", argspec, False)
        com = autocomplete.ParameterNameCompletion()
        self.assertSetEqual(
            com.matches(1, "a", funcprops=funcspec), {"apple=", "apricot="}
        )
        self.assertSetEqual(
            com.matches(2, "ba", funcprops=funcspec), {"banana="}
        )
        self.assertSetEqual(
            com.matches(3, "car", funcprops=funcspec), {"carrot="}
        )
