# -*- coding: utf-8 -*-
from __future__ import absolute_import
import inspect
import unittest
import warnings
from scrapy.utils.deprecate import warn_when_subclassed

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
                __metaclass__ = warn_when_subclassed(NewName, "message")

        self.assertEqual(w, [])

    def test_warning_on_subclassing(self):
        with warnings.catch_warnings(record=True) as w:

            class Deprecated(NewName):
                __metaclass__ = warn_when_subclassed(NewName, "message", MyWarning)

            class UserClass(Deprecated):
                pass

        self.assertEqual(len(w), 1)
        msg = w[0]
        assert issubclass(msg.category, MyWarning)
        self.assertEqual(str(msg.message), "message")
        self.assertEqual(msg.lineno, inspect.getsourcelines(UserClass)[1])
