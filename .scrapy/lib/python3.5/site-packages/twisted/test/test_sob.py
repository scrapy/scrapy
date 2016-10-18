# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import division, absolute_import

import os
import sys

from textwrap import dedent

from twisted.trial import unittest
from twisted.persisted import sob
from twisted.python import components
from twisted.python.filepath import FilePath
from twisted.python.reflect import namedAny, ObjectNotFound
from twisted.persisted.styles import Ephemeral

try:
    namedAny('Crypto.Cipher.AES')
    skipCrypto = None
except ObjectNotFound:
    skipCrypto = 'PyCrypto is required.'



class Dummy(components.Componentized):
    pass

objects = [
1,
"hello",
(1, "hello"),
[1, "hello"],
{1:"hello"},
]

class FakeModule(object):
    pass

class PersistTests(unittest.TestCase):
    def testStyles(self):
        for o in objects:
            p = sob.Persistent(o, '')
            for style in 'source pickle'.split():
                p.setStyle(style)
                p.save(filename='persisttest.'+style)
                o1 = sob.load('persisttest.'+style, style)
                self.assertEqual(o, o1)

    def testStylesBeingSet(self):
        o = Dummy()
        o.foo = 5
        o.setComponent(sob.IPersistable, sob.Persistent(o, 'lala'))
        for style in 'source pickle'.split():
            sob.IPersistable(o).setStyle(style)
            sob.IPersistable(o).save(filename='lala.'+style)
            o1 = sob.load('lala.'+style, style)
            self.assertEqual(o.foo, o1.foo)
            self.assertEqual(sob.IPersistable(o1).style, style)


    def testNames(self):
        o = [1,2,3]
        p = sob.Persistent(o, 'object')
        for style in 'source pickle'.split():
            p.setStyle(style)
            p.save()
            o1 = sob.load('object.ta'+style[0], style)
            self.assertEqual(o, o1)
            for tag in 'lala lolo'.split():
                p.save(tag)
                o1 = sob.load('object-'+tag+'.ta'+style[0], style)
                self.assertEqual(o, o1)


    def testPython(self):
        with open("persisttest.python", 'w') as f:
            f.write('foo=[1,2,3] ')
        o = sob.loadValueFromFile('persisttest.python', 'foo')
        self.assertEqual(o, [1,2,3])


    def testTypeGuesser(self):
        self.assertRaises(KeyError, sob.guessType, "file.blah")
        self.assertEqual('python', sob.guessType("file.py"))
        self.assertEqual('python', sob.guessType("file.tac"))
        self.assertEqual('python', sob.guessType("file.etac"))
        self.assertEqual('pickle', sob.guessType("file.tap"))
        self.assertEqual('pickle', sob.guessType("file.etap"))
        self.assertEqual('source', sob.guessType("file.tas"))
        self.assertEqual('source', sob.guessType("file.etas"))

    def testEverythingEphemeralGetattr(self):
        """
        L{_EverythingEphermal.__getattr__} will proxy the __main__ module as an
        L{Ephemeral} object, and during load will be transparent, but after
        load will return L{Ephemeral} objects from any accessed attributes.
        """
        self.fakeMain.testMainModGetattr = 1

        dirname = self.mktemp()
        os.mkdir(dirname)

        filename = os.path.join(dirname, 'persisttest.ee_getattr')

        global mainWhileLoading
        mainWhileLoading = None
        with open(filename, "w") as f:
            f.write(dedent("""
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
            """))

        loaded = sob.load(filename, 'source')
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

        filename = os.path.join(dirname, 'persisttest.ee_setattr')
        with open(filename, 'w') as f:
            f.write('import __main__\n')
            f.write('__main__.testMainModSetattr = 2\n')
            f.write('app = None\n')

        sob.load(filename, 'source')

        self.assertEqual(self.fakeMain.testMainModSetattr, 1)

    def testEverythingEphemeralException(self):
        """
        Test that an exception during load() won't cause _EE to mask __main__
        """
        dirname = self.mktemp()
        os.mkdir(dirname)
        filename = os.path.join(dirname, 'persisttest.ee_exception')

        with open(filename, 'w') as f:
            f.write('raise ValueError\n')

        self.assertRaises(ValueError, sob.load, filename, 'source')
        self.assertEqual(type(sys.modules['__main__']), FakeModule)

    def setUp(self):
        """
        Replace the __main__ module with a fake one, so that it can be mutated
        in tests
        """
        self.realMain = sys.modules['__main__']
        self.fakeMain = sys.modules['__main__'] = FakeModule()

    def tearDown(self):
        """
        Restore __main__ to its original value
        """
        sys.modules['__main__'] = self.realMain



class PersistentEncryptionTests(unittest.TestCase):
    """
    Unit tests for Small OBjects persistence using encryption.
    """

    if skipCrypto is not None:
        skip = skipCrypto


    def test_encryptedStyles(self):
        """
        Data can be persisted with encryption for all the supported styles.
        """
        for o in objects:
            phrase = b'once I was the king of spain'
            p = sob.Persistent(o, '')
            for style in 'source pickle'.split():
                p.setStyle(style)
                p.save(filename='epersisttest.'+style, passphrase=phrase)
                o1 = sob.load('epersisttest.'+style, style, phrase)
                self.assertEqual(o, o1)
                self.flushWarnings([p._saveTemp, sob.load])


    def test_loadValueFromFileEncryptedPython(self):
        """
        Encrypted Python data can be loaded from a file.
        """
        phrase = b'once I was the king of spain'
        with open("epersisttest.python", 'wb') as f:
            f.write(sob._encrypt(phrase, b'foo=[1,2,3]'))

        o = sob.loadValueFromFile('epersisttest.python', 'foo', phrase)

        self.assertEqual(o, [1,2,3])
        self.flushWarnings([
            sob.loadValueFromFile, self.test_loadValueFromFileEncryptedPython])


    def test_saveEncryptedDeprecation(self):
        """
        Persisting data with encryption is deprecated.
        """
        tempDir = FilePath(self.mktemp())
        tempDir.makedirs()
        persistedPath = tempDir.child('epersisttest.python')
        data = b'once I was the king of spain'
        persistance = sob.Persistent(data, 'test-data')

        persistance.save(filename=persistedPath.path, passphrase=b'some-pass')

        # Check deprecation message.
        warnings = self.flushWarnings([persistance._saveTemp])
        self.assertEqual(1, len(warnings))
        self.assertIs(DeprecationWarning, warnings[0]['category'])
        self.assertEqual(
            'Saving encrypted persisted data is deprecated since '
            'Twisted 15.5.0',
            warnings[0]['message'])
        # Check that data is still valid, even if we are deprecating this
        # functionality.
        loadedData = sob.load(
            persistedPath.path, persistance.style, b'some-pass')
        self.assertEqual(data, loadedData)
        self.flushWarnings([sob.load])


    def test_loadEncryptedDeprecation(self):
        """
        Loading encrypted persisted data is deprecated.
        """
        tempDir = FilePath(self.mktemp())
        tempDir.makedirs()
        persistedPath = tempDir.child('epersisttest.python')
        data = b'once I was the king of spain'
        persistance = sob.Persistent(data, 'test-data')
        persistance.save(filename=persistedPath.path, passphrase=b'some-pass')
        # Clean all previous warnings as save will also raise a warning.
        self.flushWarnings([persistance._saveTemp])

        loadedData = sob.load(
            persistedPath.path, persistance.style, b'some-pass')

        self.assertEqual(data, loadedData)
        warnings = self.flushWarnings([sob.load])
        self.assertEqual(1, len(warnings))
        self.assertIs(DeprecationWarning, warnings[0]['category'])
        self.assertEqual(
            'Loading encrypted persisted data is deprecated since '
            'Twisted 15.5.0',
            warnings[0]['message'])

    def test_loadValueFromFileEncryptedDeprecation(self):
        """
        Loading encrypted persisted data is deprecated.
        """
        tempDir = FilePath(self.mktemp())
        tempDir.makedirs()
        persistedPath = tempDir.child('epersisttest.python')
        persistedPath.setContent(sob._encrypt(b'some-pass', b'foo=[1,2,3]'))
        # Clean all previous warnings as _encpryt will also raise a warning.
        self.flushWarnings([
            self.test_loadValueFromFileEncryptedDeprecation])

        loadedData = sob.loadValueFromFile(
            persistedPath.path, 'foo', b'some-pass')

        self.assertEqual([1, 2, 3], loadedData)
        warnings = self.flushWarnings([sob.loadValueFromFile])
        self.assertEqual(1, len(warnings))
        self.assertIs(DeprecationWarning, warnings[0]['category'])
        self.assertEqual(
            'Loading encrypted persisted data is deprecated since '
            'Twisted 15.5.0',
            warnings[0]['message'])
