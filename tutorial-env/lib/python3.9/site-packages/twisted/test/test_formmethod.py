# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Test cases for formmethod module.
"""

from twisted.python import formmethod
from twisted.trial import unittest


class ArgumentTests(unittest.TestCase):
    def argTest(self, argKlass, testPairs, badValues, *args, **kwargs):
        arg = argKlass("name", *args, **kwargs)
        for val, result in testPairs:
            self.assertEqual(arg.coerce(val), result)
        for val in badValues:
            self.assertRaises(formmethod.InputError, arg.coerce, val)

    def test_argument(self):
        """
        Test that corce correctly raises NotImplementedError.
        """
        arg = formmethod.Argument("name")
        self.assertRaises(NotImplementedError, arg.coerce, "")

    def testString(self):
        self.argTest(formmethod.String, [("a", "a"), (1, "1"), ("", "")], ())
        self.argTest(
            formmethod.String, [("ab", "ab"), ("abc", "abc")], ("2", ""), min=2
        )
        self.argTest(
            formmethod.String, [("ab", "ab"), ("a", "a")], ("223213", "345x"), max=3
        )
        self.argTest(
            formmethod.String,
            [("ab", "ab"), ("add", "add")],
            ("223213", "x"),
            min=2,
            max=3,
        )

    def testInt(self):
        self.argTest(
            formmethod.Integer, [("3", 3), ("-2", -2), ("", None)], ("q", "2.3")
        )
        self.argTest(
            formmethod.Integer, [("3", 3), ("-2", -2)], ("q", "2.3", ""), allowNone=0
        )

    def testFloat(self):
        self.argTest(
            formmethod.Float, [("3", 3.0), ("-2.3", -2.3), ("", None)], ("q", "2.3z")
        )
        self.argTest(
            formmethod.Float,
            [("3", 3.0), ("-2.3", -2.3)],
            ("q", "2.3z", ""),
            allowNone=0,
        )

    def testChoice(self):
        choices = [("a", "apple", "an apple"), ("b", "banana", "ook")]
        self.argTest(
            formmethod.Choice,
            [("a", "apple"), ("b", "banana")],
            ("c", 1),
            choices=choices,
        )

    def testFlags(self):
        flags = [("a", "apple", "an apple"), ("b", "banana", "ook")]
        self.argTest(
            formmethod.Flags,
            [(["a"], ["apple"]), (["b", "a"], ["banana", "apple"])],
            (["a", "c"], ["fdfs"]),
            flags=flags,
        )

    def testBoolean(self):
        tests = [("yes", 1), ("", 0), ("False", 0), ("no", 0)]
        self.argTest(formmethod.Boolean, tests, ())

    def test_file(self):
        """
        Test the correctness of the coerce function.
        """
        arg = formmethod.File("name", allowNone=0)
        self.assertEqual(arg.coerce("something"), "something")
        self.assertRaises(formmethod.InputError, arg.coerce, None)
        arg2 = formmethod.File("name")
        self.assertIsNone(arg2.coerce(None))

    def testDate(self):
        goodTests = {
            ("2002", "12", "21"): (2002, 12, 21),
            ("1996", "2", "29"): (1996, 2, 29),
            ("", "", ""): None,
        }.items()
        badTests = [
            ("2002", "2", "29"),
            ("xx", "2", "3"),
            ("2002", "13", "1"),
            ("1999", "12", "32"),
            ("2002", "1"),
            ("2002", "2", "3", "4"),
        ]
        self.argTest(formmethod.Date, goodTests, badTests)

    def testRangedInteger(self):
        goodTests = {"0": 0, "12": 12, "3": 3}.items()
        badTests = ["-1", "x", "13", "-2000", "3.4"]
        self.argTest(formmethod.IntegerRange, goodTests, badTests, 0, 12)

    def testVerifiedPassword(self):
        goodTests = {("foo", "foo"): "foo", ("ab", "ab"): "ab"}.items()
        badTests = [
            ("ab", "a"),
            ("12345", "12345"),
            ("", ""),
            ("a", "a"),
            ("a",),
            ("a", "a", "a"),
        ]
        self.argTest(formmethod.VerifiedPassword, goodTests, badTests, min=2, max=4)
