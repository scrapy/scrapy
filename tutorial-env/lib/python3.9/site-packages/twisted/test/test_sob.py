# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


import os
import sys
from textwrap import dedent

from twisted.persisted import sob
from twisted.persisted.styles import Ephemeral
from twisted.python import components
from twisted.trial import unittest


class Dummy(components.Componentized):
    pass


objects = [
    1,
    "hello",
    (1, "hello"),
    [1, "hello"],
    {1: "hello"},
]


class FakeModule:
    pass


class PersistTests(unittest.TestCase):
    def testStyles(self):
        for o in objects:
            p = sob.Persistent(o, "")
            for style in "source pickle".split():
                p.setStyle(style)
                p.save(filename="persisttest." + style)
                o1 = sob.load("persisttest." + style, style)
                self.assertEqual(o, o1)

    def testStylesBeingSet(self):
        o = Dummy()
        o.foo = 5
        o.setComponent(sob.IPersistable, sob.Persistent(o, "lala"))
        for style in "source pickle".split():
            sob.IPersistable(o).setStyle(style)
            sob.IPersistable(o).save(filename="lala." + style)
            o1 = sob.load("lala." + style, style)
            self.assertEqual(o.foo, o1.foo)
            self.assertEqual(sob.IPersistable(o1).style, style)

    def testPassphraseError(self):
        """
        Calling save() with a passphrase is an error.
        """
        p = sob.Persistant(None, "object")
        self.assertRaises(TypeError, p.save, "filename.pickle", passphrase="abc")

    def testNames(self):
        o = [1, 2, 3]
        p = sob.Persistent(o, "object")
        for style in "source pickle".split():
            p.setStyle(style)
            p.save()
            o1 = sob.load("object.ta" + style[0], style)
            self.assertEqual(o, o1)
            for tag in "lala lolo".split():
                p.save(tag)
                o1 = sob.load("object-" + tag + ".ta" + style[0], style)
                self.assertEqual(o, o1)

    def testPython(self):
        with open("persisttest.python", "w") as f:
            f.write("foo=[1,2,3] ")
        o = sob.loadValueFromFile("persisttest.python", "foo")
        self.assertEqual(o, [1, 2, 3])

    def testTypeGuesser(self):
        self.assertRaises(KeyError, sob.guessType, "file.blah")
        self.assertEqual("python", sob.guessType("file.py"))
        self.assertEqual("python", sob.guessType("file.tac"))
        self.assertEqual("python", sob.guessType("file.etac"))
        self.assertEqual("pickle", sob.guessType("file.tap"))
        self.assertEqual("pickle", sob.guessType("file.etap"))
        self.assertEqual("source", sob.guessType("file.tas"))
        self.assertEqual("source", sob.guessType("file.etas"))

    def testEverythingEphemeralGetattr(self):
        """
        L{_EverythingEphermal.__getattr__} will proxy the __main__ module as an
        L{Ephemeral} object, and during load will be transparent, but after
        load will return L{Ephemeral} objects from any accessed attributes.
        """
        self.fakeMain.testMainModGetattr = 1

        dirname = self.mktemp()
        os.mkdir(dirname)

        filename = os.path.join(dirname, "persisttest.ee_getattr")

        global mainWhileLoading
        mainWhileLoading = None
        with open(filename, "w") as f:
            f.write(
                dedent(
                    """
            app = []
            import __main__
            app.append(__main__.testMainModGetattr == 1)
            try:
                __main__.somethingElse
            except AttributeError:
                app.append(True)
            else:
                app.append(False)
            from twisted.test import test_sob
            test_sob.mainWhileLoading = __main__
            """
                )
            )

        loaded = sob.load(filename, "source")
        self.assertIsInstance(loaded, list)
        self.assertTrue(loaded[0], "Expected attribute not set.")
        self.assertTrue(loaded[1], "Unexpected attribute set.")
        self.assertIsInstance(mainWhileLoading, Ephemeral)
        self.assertIsInstance(mainWhileLoading.somethingElse, Ephemeral)
        del mainWhileLoading

    def testEverythingEphemeralSetattr(self):
        """
        Verify that _EverythingEphemeral.__setattr__ won't affect __main__.
        """
        self.fakeMain.testMainModSetattr = 1

        dirname = self.mktemp()
        os.mkdir(dirname)

        filename = os.path.join(dirname, "persisttest.ee_setattr")
        with open(filename, "w") as f:
            f.write("import __main__\n")
            f.write("__main__.testMainModSetattr = 2\n")
            f.write("app = None\n")

        sob.load(filename, "source")

        self.assertEqual(self.fakeMain.testMainModSetattr, 1)

    def testEverythingEphemeralException(self):
        """
        Test that an exception during load() won't cause _EE to mask __main__
        """
        dirname = self.mktemp()
        os.mkdir(dirname)
        filename = os.path.join(dirname, "persisttest.ee_exception")

        with open(filename, "w") as f:
            f.write("raise ValueError\n")

        self.assertRaises(ValueError, sob.load, filename, "source")
        self.assertEqual(type(sys.modules["__main__"]), FakeModule)

    def setUp(self):
        """
        Replace the __main__ module with a fake one, so that it can be mutated
        in tests
        """
        self.realMain = sys.modules["__main__"]
        self.fakeMain = sys.modules["__main__"] = FakeModule()

    def tearDown(self):
        """
        Restore __main__ to its original value
        """
        sys.modules["__main__"] = self.realMain
