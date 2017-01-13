# -*- test-case-name: twisted.trial.test.test_tests -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Definitions of test cases with various interesting behaviors, to be used by
L{twisted.trial.test.test_tests} and other test modules to exercise different
features of trial's test runner.

See the L{twisted.trial.test.test_tests} module docstring for details about how
this code is arranged.
"""

from __future__ import division, absolute_import

from twisted.trial.unittest import (
    SynchronousTestCase, TestCase, SkipTest, FailTest)


class SkippingMixin(object):
    def test_skip1(self):
        raise SkipTest('skip1')

    def test_skip2(self):
        raise RuntimeError("I should not get raised")
    test_skip2.skip = 'skip2'

    def test_skip3(self):
        self.fail('I should not fail')
    test_skip3.skip = 'skip3'



class SynchronousSkipping(SkippingMixin, SynchronousTestCase):
    pass



class AsynchronousSkipping(SkippingMixin, TestCase):
    pass



class SkippingSetUpMixin(object):
    def setUp(self):
        raise SkipTest('skipSetUp')

    def test_1(self):
        pass

    def test_2(self):
        pass


class SynchronousSkippingSetUp(SkippingSetUpMixin, SynchronousTestCase):
    pass



class AsynchronousSkippingSetUp(SkippingSetUpMixin, TestCase):
    pass



class DeprecatedReasonlessSkipMixin(object):
    def test_1(self):
        raise SkipTest()



class SynchronousDeprecatedReasonlessSkip(
    DeprecatedReasonlessSkipMixin, SynchronousTestCase):
    pass



class AsynchronousDeprecatedReasonlessSkip(
    DeprecatedReasonlessSkipMixin, TestCase):
    pass



class SkippedClassMixin(object):
    skip = 'class'
    def setUp(self):
        self.__class__._setUpRan = True
    def test_skip1(self):
        raise SkipTest('skip1')
    def test_skip2(self):
        raise RuntimeError("Ought to skip me")
    test_skip2.skip = 'skip2'
    def test_skip3(self):
        pass
    def test_skip4(self):
        raise RuntimeError("Skip me too")



class SynchronousSkippedClass(SkippedClassMixin, SynchronousTestCase):
    pass



class AsynchronousSkippedClass(SkippedClassMixin, TestCase):
    pass



class TodoMixin(object):
    def test_todo1(self):
        self.fail("deliberate failure")
    test_todo1.todo = "todo1"

    def test_todo2(self):
        raise RuntimeError("deliberate error")
    test_todo2.todo = "todo2"

    def test_todo3(self):
        """unexpected success"""
    test_todo3.todo = 'todo3'




class SynchronousTodo(TodoMixin, SynchronousTestCase):
    pass



class AsynchronousTodo(TodoMixin, TestCase):
    pass



class SetUpTodoMixin(object):
    def setUp(self):
        raise RuntimeError("deliberate error")

    def test_todo1(self):
        pass
    test_todo1.todo = "setUp todo1"



class SynchronousSetUpTodo(SetUpTodoMixin, SynchronousTestCase):
    pass



class AsynchronousSetUpTodo(SetUpTodoMixin, TestCase):
    pass



class TearDownTodoMixin(object):
    def tearDown(self):
        raise RuntimeError("deliberate error")

    def test_todo1(self):
        pass
    test_todo1.todo = "tearDown todo1"



class SynchronousTearDownTodo(TearDownTodoMixin, SynchronousTestCase):
    pass



class AsynchronousTearDownTodo(TearDownTodoMixin, TestCase):
    pass



class TodoClassMixin(object):
    todo = "class"
    def test_todo1(self):
        pass
    test_todo1.todo = "method"
    def test_todo2(self):
        pass
    def test_todo3(self):
        self.fail("Deliberate Failure")
    test_todo3.todo = "method"
    def test_todo4(self):
        self.fail("Deliberate Failure")



class SynchronousTodoClass(TodoClassMixin, SynchronousTestCase):
    pass



class AsynchronousTodoClass(TodoClassMixin, TestCase):
    pass



class StrictTodoMixin(object):
    def test_todo1(self):
        raise RuntimeError("expected failure")
    test_todo1.todo = (RuntimeError, "todo1")

    def test_todo2(self):
        raise RuntimeError("expected failure")
    test_todo2.todo = ((RuntimeError, OSError), "todo2")

    def test_todo3(self):
        raise RuntimeError("we had no idea!")
    test_todo3.todo = (OSError, "todo3")

    def test_todo4(self):
        raise RuntimeError("we had no idea!")
    test_todo4.todo = ((OSError, SyntaxError), "todo4")

    def test_todo5(self):
        self.fail("deliberate failure")
    test_todo5.todo = (FailTest, "todo5")

    def test_todo6(self):
        self.fail("deliberate failure")
    test_todo6.todo = (RuntimeError, "todo6")

    def test_todo7(self):
        pass
    test_todo7.todo = (RuntimeError, "todo7")



class SynchronousStrictTodo(StrictTodoMixin, SynchronousTestCase):
    pass



class AsynchronousStrictTodo(StrictTodoMixin, TestCase):
    pass



class AddCleanupMixin(object):
    def setUp(self):
        self.log = ['setUp']

    def brokenSetUp(self):
        self.log = ['setUp']
        raise RuntimeError("Deliberate failure")

    def skippingSetUp(self):
        self.log = ['setUp']
        raise SkipTest("Don't do this")

    def append(self, thing):
        self.log.append(thing)

    def tearDown(self):
        self.log.append('tearDown')

    def runTest(self):
        self.log.append('runTest')



class SynchronousAddCleanup(AddCleanupMixin, SynchronousTestCase):
    pass



class AsynchronousAddCleanup(AddCleanupMixin, TestCase):
    pass
