import ast
import numbers
import sys
import unittest

from bpython.simpleeval import (
    simple_eval,
    evaluate_current_expression,
    EvaluationError,
)


class TestSimpleEval(unittest.TestCase):
    def assertMatchesStdlib(self, expr):
        self.assertEqual(ast.literal_eval(expr), simple_eval(expr))

    def test_matches_stdlib(self):
        """Should match the stdlib literal_eval if no names or indexing"""
        self.assertMatchesStdlib("[1]")
        self.assertMatchesStdlib("{(1,): [2,3,{}]}")
        self.assertMatchesStdlib("{1, 2}")

    @unittest.skipUnless(
        sys.version_info[:2] >= (3, 9), "Only Python3.9 evaluates set()"
    )
    def test_matches_stdlib_set_literal(self):
        """set() is evaluated"""
        self.assertMatchesStdlib("set()")

    def test_indexing(self):
        """Literals can be indexed into"""
        self.assertEqual(simple_eval("[1,2][0]"), 1)

    def test_name_lookup(self):
        """Names can be looked up in a namespace"""
        self.assertEqual(simple_eval("a", {"a": 1}), 1)
        self.assertEqual(simple_eval("map"), map)

    def test_name_lookup_indexing(self):
        """Names can be looked up in a namespace"""
        self.assertEqual(simple_eval("a[b]", {"a": {"c": 1}, "b": "c"}), 1)

    def test_lookup_on_suspicious_types(self):
        class FakeDict:
            pass

        with self.assertRaises(ValueError):
            simple_eval("a[1]", {"a": FakeDict()})

        class TrickyDict(dict):
            def __getitem__(self, index):
                self.fail("doing key lookup isn't safe")

        with self.assertRaises(ValueError):
            simple_eval("a[1]", {"a": TrickyDict()})

        class SchrodingersDict(dict):
            def __getattribute__(inner_self, attr):
                self.fail("doing attribute lookup might have side effects")

        with self.assertRaises(ValueError):
            simple_eval("a[1]", {"a": SchrodingersDict()})

        class SchrodingersCatsDict(dict):
            def __getattr__(inner_self, attr):
                self.fail("doing attribute lookup might have side effects")

        with self.assertRaises(ValueError):
            simple_eval("a[1]", {"a": SchrodingersDict()})

    def test_operators_on_suspicious_types(self):
        class Spam(numbers.Number):
            def __add__(inner_self, other):
                self.fail("doing attribute lookup might have side effects")

        with self.assertRaises(ValueError):
            simple_eval("a + 1", {"a": Spam()})

    def test_operators_on_numbers(self):
        self.assertEqual(simple_eval("-2"), -2)
        self.assertEqual(simple_eval("1 + 1"), 2)
        self.assertEqual(simple_eval("a - 2", {"a": 1}), -1)
        with self.assertRaises(ValueError):
            simple_eval("2 * 3")
        with self.assertRaises(ValueError):
            simple_eval("2 ** 3")

    def test_function_calls_raise(self):
        with self.assertRaises(ValueError):
            simple_eval("1()")

    def test_nonexistant_names_raise(self):
        with self.assertRaises(EvaluationError):
            simple_eval("a")

    def test_attribute_access(self):
        class Foo:
            abc = 1

        self.assertEqual(simple_eval("foo.abc", {"foo": Foo()}), 1)


class TestEvaluateCurrentExpression(unittest.TestCase):
    def assertEvaled(self, line, value, ns=None):
        assert line.count("|") == 1
        cursor_offset = line.find("|")
        line = line.replace("|", "")
        self.assertEqual(
            evaluate_current_expression(cursor_offset, line, ns), value
        )

    def assertCannotEval(self, line, ns=None):
        assert line.count("|") == 1
        cursor_offset = line.find("|")
        line = line.replace("|", "")
        with self.assertRaises(EvaluationError):
            evaluate_current_expression(cursor_offset, line, ns)

    def test_simple(self):
        self.assertEvaled("[1].a|bc", [1])
        self.assertEvaled("[1].abc|", [1])
        self.assertEvaled("[1].|abc", [1])
        self.assertEvaled("[1]. |abc", [1])
        self.assertEvaled("[1] .|abc", [1])
        self.assertCannotEval("[1].abc |", [1])
        self.assertCannotEval("[1]. abc |", [1])
        self.assertCannotEval("[2][1].a|bc", [1])

    def test_nonsense(self):
        self.assertEvaled("!@#$ [1].a|bc", [1])
        self.assertEvaled("--- [2][0].a|bc", 2)
        self.assertCannotEval('"asdf".centered()[1].a|bc')
        self.assertEvaled('"asdf"[1].a|bc', "s")

    def test_with_namespace(self):
        self.assertEvaled("a[1].a|bc", "d", {"a": "adsf"})
        self.assertCannotEval("a[1].a|bc", {})


if __name__ == "__main__":
    unittest.main()
