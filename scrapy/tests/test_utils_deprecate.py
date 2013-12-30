# -*- coding: utf-8 -*-
from __future__ import absolute_import
import inspect
import unittest
import warnings
from scrapy.utils.deprecate import deprecated_base_class

class MyWarning(UserWarning):
    pass

class SomeBaseClass(object):
    pass

class NewName(SomeBaseClass):
    pass


class WarnWhenSubclassedTest(unittest.TestCase):

    def test_no_warning_on_definition(self):
        with warnings.catch_warnings(record=True) as w:

            class Deprecated(NewName):
                __metaclass__ = deprecated_base_class(NewName, "message")

        self.assertEqual(w, [])

    def test_warning_on_subclassing(self):
        with warnings.catch_warnings(record=True) as w:

            class Deprecated(NewName):
                __metaclass__ = deprecated_base_class(NewName, "message", MyWarning)

            class UserClass(Deprecated):
                pass

        self.assertEqual(len(w), 1)
        msg = w[0]
        assert issubclass(msg.category, MyWarning)
        self.assertEqual(str(msg.message), "message")
        self.assertEqual(msg.lineno, inspect.getsourcelines(UserClass)[1])

    def test_warning_auto_message(self):
        with warnings.catch_warnings(record=True) as w:

            class Deprecated(NewName):
                __metaclass__ = deprecated_base_class(NewName)

            class UserClass2(Deprecated):
                pass

        msg = str(w[0].message)
        self.assertIn("scrapy.tests.test_utils_deprecate.NewName", msg)
        # this doesn't work:
        # self.assertIn("scrapy.tests.test_utils_deprecate.Deprecated", msg)

    def test_issubclass(self):
        with warnings.catch_warnings(record=True):

            class DeprecatedName(NewName):
                __metaclass__ = deprecated_base_class(NewName, "message", MyWarning)

            class UpdatedUserClass1(NewName):
                pass

            class UpdatedUserClass1a(NewName):
                pass

            class OutdatedUserClass1(DeprecatedName):
                pass

            class UnrelatedClass(object):
                pass

            class OldStyleClass:
                pass

        assert issubclass(UpdatedUserClass1, NewName)
        assert issubclass(UpdatedUserClass1a, NewName)
        assert issubclass(UpdatedUserClass1, DeprecatedName)
        assert issubclass(UpdatedUserClass1a, DeprecatedName)
        assert issubclass(OutdatedUserClass1, DeprecatedName)
        assert not issubclass(UnrelatedClass, DeprecatedName)
        assert not issubclass(OldStyleClass, DeprecatedName)
        assert not issubclass(OldStyleClass, DeprecatedName)

        self.assertRaises(TypeError, issubclass, object(), DeprecatedName)

    def test_isinstance(self):
        with warnings.catch_warnings(record=True):

            class DeprecatedName(NewName):
                __metaclass__ = deprecated_base_class(NewName, "message", MyWarning)

            class UpdatedUserClass2(NewName):
                pass

            class UpdatedUserClass2a(NewName):
                pass

            class OutdatedUserClass2(DeprecatedName):
                pass

            class UnrelatedClass(object):
                pass

            class OldStyleClass:
                pass

        assert isinstance(UpdatedUserClass2(), NewName)
        assert isinstance(UpdatedUserClass2a(), NewName)
        assert isinstance(UpdatedUserClass2(), DeprecatedName)
        assert isinstance(UpdatedUserClass2a(), DeprecatedName)
        assert isinstance(OutdatedUserClass2(), DeprecatedName)
        assert not isinstance(UnrelatedClass(), DeprecatedName)
        assert not isinstance(OldStyleClass(), DeprecatedName)

    def test_invalid_usage(self):

        class SomeClass(object):
            pass

        def define_invalid():
            class DeprecatedName(NewName):
                __metaclass__ = deprecated_base_class(SomeClass)

        self.assertRaises(ValueError, define_invalid)
