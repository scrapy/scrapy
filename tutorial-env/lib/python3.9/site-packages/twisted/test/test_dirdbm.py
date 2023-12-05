# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test cases for dirdbm module.
"""

import shutil
from base64 import b64decode

from twisted.persisted import dirdbm
from twisted.python import rebuild
from twisted.python.filepath import FilePath
from twisted.trial import unittest


class DirDbmTests(unittest.TestCase):
    def setUp(self):
        self.path = FilePath(self.mktemp())
        self.dbm = dirdbm.open(self.path.path)
        self.items = ((b"abc", b"foo"), (b"/lalal", b"\000\001"), (b"\000\012", b"baz"))

    def test_all(self):
        k = b64decode("//==")
        self.dbm[k] = b"a"
        self.dbm[k] = b"a"
        self.assertEqual(self.dbm[k], b"a")

    def test_rebuildInteraction(self):
        s = dirdbm.Shelf("dirdbm.rebuild.test")
        s[b"key"] = b"value"
        rebuild.rebuild(dirdbm)

    def test_dbm(self):
        d = self.dbm

        # Insert keys
        keys = []
        values = set()
        for k, v in self.items:
            d[k] = v
            keys.append(k)
            values.add(v)
        keys.sort()

        # Check they exist
        for k, v in self.items:
            self.assertIn(k, d)
            self.assertEqual(d[k], v)

        # Check non existent key
        try:
            d[b"XXX"]
        except KeyError:
            pass
        else:
            assert 0, "didn't raise KeyError on non-existent key"

        # Check keys(), values() and items()
        dbkeys = d.keys()
        dbvalues = set(d.values())
        dbitems = set(d.items())
        dbkeys.sort()
        items = set(self.items)
        self.assertEqual(
            keys,
            dbkeys,
            f".keys() output didn't match: {repr(keys)} != {repr(dbkeys)}",
        )
        self.assertEqual(
            values,
            dbvalues,
            ".values() output didn't match: {} != {}".format(
                repr(values), repr(dbvalues)
            ),
        )
        self.assertEqual(
            items,
            dbitems,
            f"items() didn't match: {repr(items)} != {repr(dbitems)}",
        )

        copyPath = self.mktemp()
        d2 = d.copyTo(copyPath)

        copykeys = d.keys()
        copyvalues = set(d.values())
        copyitems = set(d.items())
        copykeys.sort()

        self.assertEqual(
            dbkeys,
            copykeys,
            ".copyTo().keys() didn't match: {} != {}".format(
                repr(dbkeys), repr(copykeys)
            ),
        )
        self.assertEqual(
            dbvalues,
            copyvalues,
            ".copyTo().values() didn't match: %s != %s"
            % (repr(dbvalues), repr(copyvalues)),
        )
        self.assertEqual(
            dbitems,
            copyitems,
            ".copyTo().items() didn't match: %s != %s"
            % (repr(dbkeys), repr(copyitems)),
        )

        d2.clear()
        self.assertTrue(
            len(d2.keys()) == len(d2.values()) == len(d2.items()) == len(d2) == 0,
            ".clear() failed",
        )
        self.assertNotEqual(len(d), len(d2))
        shutil.rmtree(copyPath)

        # Delete items
        for k, v in self.items:
            del d[k]
            self.assertNotIn(
                k, d, "key is still in database, even though we deleted it"
            )
        self.assertEqual(len(d.keys()), 0, "database has keys")
        self.assertEqual(len(d.values()), 0, "database has values")
        self.assertEqual(len(d.items()), 0, "database has items")
        self.assertEqual(len(d), 0, "database has items")

    def test_modificationTime(self):
        import time

        # The mtime value for files comes from a different place than the
        # gettimeofday() system call. On linux, gettimeofday() can be
        # slightly ahead (due to clock drift which gettimeofday() takes into
        # account but which open()/write()/close() do not), and if we are
        # close to the edge of the next second, time.time() can give a value
        # which is larger than the mtime which results from a subsequent
        # write(). I consider this a kernel bug, but it is beyond the scope
        # of this test. Thus we keep the range of acceptability to 3 seconds time.
        # -warner
        self.dbm[b"k"] = b"v"
        self.assertTrue(abs(time.time() - self.dbm.getModificationTime(b"k")) <= 3)
        self.assertRaises(KeyError, self.dbm.getModificationTime, b"nokey")

    def test_recovery(self):
        """
        DirDBM: test recovery from directory after a faked crash
        """
        k = self.dbm._encode(b"key1")
        with self.path.child(k + b".rpl").open(mode="wb") as f:
            f.write(b"value")

        k2 = self.dbm._encode(b"key2")
        with self.path.child(k2).open(mode="wb") as f:
            f.write(b"correct")
        with self.path.child(k2 + b".rpl").open(mode="wb") as f:
            f.write(b"wrong")

        with self.path.child("aa.new").open(mode="wb") as f:
            f.write(b"deleted")

        dbm = dirdbm.DirDBM(self.path.path)
        self.assertEqual(dbm[b"key1"], b"value")
        self.assertEqual(dbm[b"key2"], b"correct")
        self.assertFalse(self.path.globChildren("*.new"))
        self.assertFalse(self.path.globChildren("*.rpl"))

    def test_nonStringKeys(self):
        """
        L{dirdbm.DirDBM} operations only support string keys: other types
        should raise a L{TypeError}.
        """
        self.assertRaises(TypeError, self.dbm.__setitem__, 2, "3")
        try:
            self.assertRaises(TypeError, self.dbm.__setitem__, "2", 3)
        except unittest.FailTest:
            # dirdbm.Shelf.__setitem__ supports non-string values
            self.assertIsInstance(self.dbm, dirdbm.Shelf)
        self.assertRaises(TypeError, self.dbm.__getitem__, 2)
        self.assertRaises(TypeError, self.dbm.__delitem__, 2)
        self.assertRaises(TypeError, self.dbm.has_key, 2)
        self.assertRaises(TypeError, self.dbm.__contains__, 2)
        self.assertRaises(TypeError, self.dbm.getModificationTime, 2)

    def test_failSet(self):
        """
        Failure path when setting an item.
        """

        def _writeFail(path, data):
            path.setContent(data)
            raise OSError("fail to write")

        self.dbm[b"failkey"] = b"test"
        self.patch(self.dbm, "_writeFile", _writeFail)
        self.assertRaises(IOError, self.dbm.__setitem__, b"failkey", b"test2")


class ShelfTests(DirDbmTests):
    def setUp(self):
        self.path = FilePath(self.mktemp())
        self.dbm = dirdbm.Shelf(self.path.path)
        self.items = (
            (b"abc", b"foo"),
            (b"/lalal", b"\000\001"),
            (b"\000\012", b"baz"),
            (b"int", 12),
            (b"float", 12.0),
            (b"tuple", (None, 12)),
        )


testCases = [DirDbmTests, ShelfTests]
