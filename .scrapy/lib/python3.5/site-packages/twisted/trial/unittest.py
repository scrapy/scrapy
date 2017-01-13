# -*- test-case-name: twisted.trial.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Things likely to be used by writers of unit tests.
"""

from __future__ import division, absolute_import

# Define the public API from the two implementation modules
from twisted.trial._synctest import (
    FailTest, SkipTest, SynchronousTestCase, PyUnitResultAdapter, Todo,
    makeTodo)
from twisted.trial._asynctest import TestCase
from twisted.trial._asyncrunner import (
    TestSuite, TestDecorator, decorate)

# Further obscure the origins of these objects, to reduce surprise (and this is
# what the values were before code got shuffled around between files, but was
# otherwise unchanged).
FailTest.__module__ = SkipTest.__module__ = __name__

__all__ = [
    'decorate',
    'FailTest',
    'makeTodo',
    'PyUnitResultAdapter',
    'SkipTest',
    'SynchronousTestCase',
    'TestCase',
    'TestDecorator',
    'TestSuite',
    'Todo',
    ]
