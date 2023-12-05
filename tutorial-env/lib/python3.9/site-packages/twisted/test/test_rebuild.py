# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


import os
import sys
import types

from twisted.python import rebuild
from twisted.trial.unittest import TestCase
from . import crash_test_dummy

f = crash_test_dummy.foo


class Foo:
    pass


class Bar(Foo):
    pass


class Baz:
    pass


class Buz(Bar, Baz):
    pass


class HashRaisesRuntimeError:
    """
    Things that don't hash (raise an Exception) should be ignored by the
    rebuilder.

    @ivar hashCalled: C{bool} set to True when __hash__ is called.
    """

    def __init__(self):
        self.hashCalled = False

    def __hash__(self):
        self.hashCalled = True
        raise RuntimeError("not a TypeError!")


# Set in test_hashException
unhashableObject = None


class RebuildTests(TestCase):
    """
    Simple testcase for rebuilding, to at least exercise the code.
    """

    def setUp(self):
        self.libPath = self.mktemp()
        os.mkdir(self.libPath)
        self.fakelibPath = os.path.join(self.libPath, "twisted_rebuild_fakelib")
        os.mkdir(self.fakelibPath)
        open(os.path.join(self.fakelibPath, "__init__.py"), "w").close()
        sys.path.insert(0, self.libPath)

    def tearDown(self):
        sys.path.remove(self.libPath)

    def test_FileRebuild(self):
        import shutil
        import time

        from twisted.python.util import sibpath

        shutil.copyfile(
            sibpath(__file__, "myrebuilder1.py"),
            os.path.join(self.fakelibPath, "myrebuilder.py"),
        )
        from twisted_rebuild_fakelib import myrebuilder  # type: ignore[import]

        a = myrebuilder.A()
        b = myrebuilder.B()
        i = myrebuilder.Inherit()
        self.assertEqual(a.a(), "a")
        # Necessary because the file has not "changed" if a second has not gone
        # by in unix.  This sucks, but it's not often that you'll be doing more
        # than one reload per second.
        time.sleep(1.1)
        shutil.copyfile(
            sibpath(__file__, "myrebuilder2.py"),
            os.path.join(self.fakelibPath, "myrebuilder.py"),
        )
        rebuild.rebuild(myrebuilder)
        b2 = myrebuilder.B()
        self.assertEqual(b2.b(), "c")
        self.assertEqual(b.b(), "c")
        self.assertEqual(i.a(), "d")
        self.assertEqual(a.a(), "b")

    def test_Rebuild(self):
        """
        Rebuilding an unchanged module.
        """
        # This test would actually pass if rebuild was a no-op, but it
        # ensures rebuild doesn't break stuff while being a less
        # complex test than testFileRebuild.

        x = crash_test_dummy.X("a")

        rebuild.rebuild(crash_test_dummy, doLog=False)
        # Instance rebuilding is triggered by attribute access.
        x.do()
        self.assertEqual(x.__class__, crash_test_dummy.X)

        self.assertEqual(f, crash_test_dummy.foo)

    def test_ComponentInteraction(self):
        x = crash_test_dummy.XComponent()
        x.setAdapter(crash_test_dummy.IX, crash_test_dummy.XA)
        x.getComponent(crash_test_dummy.IX)
        rebuild.rebuild(crash_test_dummy, 0)
        newComponent = x.getComponent(crash_test_dummy.IX)

        newComponent.method()

        self.assertEqual(newComponent.__class__, crash_test_dummy.XA)

        # Test that a duplicate registerAdapter is not allowed
        from twisted.python import components

        self.assertRaises(
            ValueError,
            components.registerAdapter,
            crash_test_dummy.XA,
            crash_test_dummy.X,
            crash_test_dummy.IX,
        )

    def test_UpdateInstance(self):
        global Foo, Buz

        b = Buz()

        class Foo:
            def foo(self):
                """
                Dummy method
                """

        class Buz(Bar, Baz):
            x = 10

        rebuild.updateInstance(b)
        assert hasattr(b, "foo"), "Missing method on rebuilt instance"
        assert hasattr(b, "x"), "Missing class attribute on rebuilt instance"

    def test_BananaInteraction(self):
        from twisted.python import rebuild
        from twisted.spread import banana

        rebuild.latestClass(banana.Banana)

    def test_hashException(self):
        """
        Rebuilding something that has a __hash__ that raises a non-TypeError
        shouldn't cause rebuild to die.
        """
        global unhashableObject
        unhashableObject = HashRaisesRuntimeError()

        def _cleanup():
            global unhashableObject
            unhashableObject = None

        self.addCleanup(_cleanup)
        rebuild.rebuild(rebuild)
        self.assertTrue(unhashableObject.hashCalled)

    def test_Sensitive(self):
        """
        L{twisted.python.rebuild.Sensitive}
        """
        from twisted.python import rebuild
        from twisted.python.rebuild import Sensitive

        class TestSensitive(Sensitive):
            def test_method(self):
                """
                Dummy method
                """

        testSensitive = TestSensitive()
        testSensitive.rebuildUpToDate()
        self.assertFalse(testSensitive.needRebuildUpdate())

        # Test rebuilding a builtin class
        newException = rebuild.latestClass(Exception)
        self.assertEqual(repr(Exception), repr(newException))
        self.assertEqual(newException, testSensitive.latestVersionOf(newException))

        # Test types.MethodType on method in class
        self.assertEqual(
            TestSensitive.test_method,
            testSensitive.latestVersionOf(TestSensitive.test_method),
        )
        # Test types.MethodType on method in instance of class
        self.assertEqual(
            testSensitive.test_method,
            testSensitive.latestVersionOf(testSensitive.test_method),
        )
        # Test a class
        self.assertEqual(TestSensitive, testSensitive.latestVersionOf(TestSensitive))

        def myFunction():
            """
            Dummy method
            """

        # Test types.FunctionType
        self.assertEqual(myFunction, testSensitive.latestVersionOf(myFunction))


class NewStyleTests(TestCase):
    """
    Tests for rebuilding new-style classes of various sorts.
    """

    def setUp(self):
        self.m = types.ModuleType("whipping")
        sys.modules["whipping"] = self.m

    def tearDown(self):
        del sys.modules["whipping"]
        del self.m

    def test_slots(self):
        """
        Try to rebuild a new style class with slots defined.
        """
        classDefinition = "class SlottedClass:\n" "    __slots__ = ['a']\n"

        exec(classDefinition, self.m.__dict__)
        inst = self.m.SlottedClass()
        inst.a = 7
        exec(classDefinition, self.m.__dict__)
        rebuild.updateInstance(inst)
        self.assertEqual(inst.a, 7)
        self.assertIs(type(inst), self.m.SlottedClass)

    def test_typeSubclass(self):
        """
        Try to rebuild a base type subclass.
        """
        classDefinition = "class ListSubclass(list):\n" "    pass\n"

        exec(classDefinition, self.m.__dict__)
        inst = self.m.ListSubclass()
        inst.append(2)
        exec(classDefinition, self.m.__dict__)
        rebuild.updateInstance(inst)
        self.assertEqual(inst[0], 2)
        self.assertIs(type(inst), self.m.ListSubclass)
