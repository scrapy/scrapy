# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.conch.client.knownhosts}.
"""


import os
from binascii import Error as BinasciiError, a2b_base64, b2a_base64
from unittest import skipIf

from zope.interface.verify import verifyObject

from twisted.conch.error import HostKeyChanged, InvalidEntry, UserRejectedKey
from twisted.conch.interfaces import IKnownHostEntry
from twisted.internet.defer import Deferred
from twisted.python.compat import networkString
from twisted.python.filepath import FilePath
from twisted.python.reflect import requireModule
from twisted.test.testutils import ComparisonTestsMixin
from twisted.trial.unittest import TestCase

if requireModule("cryptography") and requireModule("pyasn1"):
    from twisted.conch.client import default
    from twisted.conch.client.knownhosts import (
        ConsoleUI,
        HashedEntry,
        KnownHostsFile,
        PlainEntry,
        UnparsedEntry,
    )
    from twisted.conch.ssh.keys import BadKeyError, Key
    from twisted.conch.test import keydata
else:
    skip = "cryptography and PyASN1 required for twisted.conch.knownhosts."


sampleEncodedKey = (
    b"AAAAB3NzaC1yc2EAAAABIwAAAQEAsV0VMRbGmzhqxxayLRHmvnFvtyNqgbNKV46dU1bVFB+3y"
    b"tNvue4Riqv/SVkPRNwMb7eWH29SviXaBxUhYyzKkDoNUq3rTNnH1Vnif6d6X4JCrUb5d3W+Dm"
    b"YClyJrZ5HgD/hUpdSkTRqdbQ2TrvSAxRacj+vHHT4F4dm1bJSewm3B2D8HVOoi/CbVh3dsIiC"
    b"dp8VltdZx4qYVfYe2LwVINCbAa3d3tj9ma7RVfw3OH2Mfb+toLd1N5tBQFb7oqTt2nC6I/6Bd"
    b"4JwPUld+IEitw/suElq/AIJVQXXujeyiZlea90HE65U2mF1ytr17HTAIT2ySokJWyuBANGACk"
    b"6iIaw=="
)

otherSampleEncodedKey = (
    b"AAAAB3NzaC1yc2EAAAABIwAAAIEAwaeCZd3UCuPXhX39+/p9qO028jTF76DMVd9mPvYVDVXuf"
    b"WckKZauF7+0b7qm+ChT7kan6BzRVo4++gCVNfAlMzLysSt3ylmOR48tFpAfygg9UCX3DjHz0E"
    b"lOOUKh3iifc9aUShD0OPaK3pR5JJ8jfiBfzSYWt/hDi/iZ4igsSs8="
)

thirdSampleEncodedKey = (
    b"AAAAB3NzaC1yc2EAAAABIwAAAQEAl/TQakPkePlnwCBRPitIVUTg6Z8VzN1en+DGkyo/evkmLw"
    b"7o4NWR5qbysk9A9jXW332nxnEuAnbcCam9SHe1su1liVfyIK0+3bdn0YRB0sXIbNEtMs2LtCho"
    b"/aV3cXPS+Cf1yut3wvIpaRnAzXxuKPCTXQ7/y0IXa8TwkRBH58OJa3RqfQ/NsSp5SAfdsrHyH2"
    b"aitiVKm2jfbTKzSEqOQG/zq4J9GXTkq61gZugory/Tvl5/yPgSnOR6C9jVOMHf27ZPoRtyj9SY"
    b"343Hd2QHiIE0KPZJEgCynKeWoKz8v6eTSK8n4rBnaqWdp8MnGZK1WGy05MguXbyCDuTC8AmJXQ"
    b"=="
)

ecdsaSampleEncodedKey = (
    b"AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBIFwh3/zBANyPPIE60"
    b"SMMfdKMYo3OvfvzGLZphzuKrzSt0q4uF+/iYqtYiHhryAwU/fDWlUQ9kck9f+IlpsNtY4="
)

sampleKey = a2b_base64(sampleEncodedKey)
otherSampleKey = a2b_base64(otherSampleEncodedKey)
thirdSampleKey = a2b_base64(thirdSampleEncodedKey)
ecdsaSampleKey = a2b_base64(ecdsaSampleEncodedKey)

samplePlaintextLine = b"www.twistedmatrix.com ssh-rsa " + sampleEncodedKey + b"\n"

otherSamplePlaintextLine = b"divmod.com ssh-rsa " + otherSampleEncodedKey + b"\n"

sampleHostIPLine = (
    b"www.twistedmatrix.com,198.49.126.131 ssh-rsa " + sampleEncodedKey + b"\n"
)

sampleHashedLine = (
    b"|1|gJbSEPBG9ZSBoZpHNtZBD1bHKBA=|bQv+0Xa0dByrwkA1EB0E7Xop/Fo= ssh-rsa "
    + sampleEncodedKey
    + b"\n"
)


class EntryTestsMixin:
    """
    Tests for implementations of L{IKnownHostEntry}.  Subclasses must set the
    'entry' attribute to a provider of that interface, the implementation of
    that interface under test.

    @ivar entry: a provider of L{IKnownHostEntry} with a hostname of
    www.twistedmatrix.com and an RSA key of sampleKey.
    """

    def test_providesInterface(self):
        """
        The given entry should provide IKnownHostEntry.
        """
        verifyObject(IKnownHostEntry, self.entry)

    def test_fromString(self):
        """
        Constructing a plain text entry from an unhashed known_hosts entry will
        result in an L{IKnownHostEntry} provider with 'keyString', 'hostname',
        and 'keyType' attributes.  While outside the interface in question,
        these attributes are held in common by L{PlainEntry} and L{HashedEntry}
        implementations; other implementations should override this method in
        subclasses.
        """
        entry = self.entry
        self.assertEqual(entry.publicKey, Key.fromString(sampleKey))
        self.assertEqual(entry.keyType, b"ssh-rsa")

    def test_matchesKey(self):
        """
        L{IKnownHostEntry.matchesKey} checks to see if an entry matches a given
        SSH key.
        """
        twistedmatrixDotCom = Key.fromString(sampleKey)
        divmodDotCom = Key.fromString(otherSampleKey)
        self.assertEqual(True, self.entry.matchesKey(twistedmatrixDotCom))
        self.assertEqual(False, self.entry.matchesKey(divmodDotCom))

    def test_matchesHost(self):
        """
        L{IKnownHostEntry.matchesHost} checks to see if an entry matches a
        given hostname.
        """
        self.assertTrue(self.entry.matchesHost(b"www.twistedmatrix.com"))
        self.assertFalse(self.entry.matchesHost(b"www.divmod.com"))


class PlainEntryTests(EntryTestsMixin, TestCase):
    """
    Test cases for L{PlainEntry}.
    """

    plaintextLine = samplePlaintextLine
    hostIPLine = sampleHostIPLine

    def setUp(self):
        """
        Set 'entry' to a sample plain-text entry with sampleKey as its key.
        """
        self.entry = PlainEntry.fromString(self.plaintextLine)

    def test_matchesHostIP(self):
        """
        A "hostname,ip" formatted line will match both the host and the IP.
        """
        self.entry = PlainEntry.fromString(self.hostIPLine)
        self.assertTrue(self.entry.matchesHost(b"198.49.126.131"))
        self.test_matchesHost()

    def test_toString(self):
        """
        L{PlainEntry.toString} generates the serialized OpenSSL format string
        for the entry, sans newline.
        """
        self.assertEqual(self.entry.toString(), self.plaintextLine.rstrip(b"\n"))
        multiHostEntry = PlainEntry.fromString(self.hostIPLine)
        self.assertEqual(multiHostEntry.toString(), self.hostIPLine.rstrip(b"\n"))


class PlainTextWithCommentTests(PlainEntryTests):
    """
    Test cases for L{PlainEntry} when parsed from a line with a comment.
    """

    plaintextLine = samplePlaintextLine[:-1] + b" plain text comment.\n"
    hostIPLine = sampleHostIPLine[:-1] + b" text following host/IP line\n"


class HashedEntryTests(EntryTestsMixin, ComparisonTestsMixin, TestCase):
    """
    Tests for L{HashedEntry}.

    This suite doesn't include any tests for host/IP pairs because hashed
    entries store IP addresses the same way as hostnames and does not support
    comma-separated lists.  (If you hash the IP and host together you can't
    tell if you've got the key already for one or the other.)
    """

    hashedLine = sampleHashedLine

    def setUp(self):
        """
        Set 'entry' to a sample hashed entry for twistedmatrix.com with
        sampleKey as its key.
        """
        self.entry = HashedEntry.fromString(self.hashedLine)

    def test_toString(self):
        """
        L{HashedEntry.toString} generates the serialized OpenSSL format string
        for the entry, sans the newline.
        """
        self.assertEqual(self.entry.toString(), self.hashedLine.rstrip(b"\n"))

    def test_equality(self):
        """
        Two L{HashedEntry} instances compare equal if and only if they represent
        the same host and key in exactly the same way: the host salt, host hash,
        public key type, public key, and comment fields must all be equal.
        """
        hostSalt = b"gJbSEPBG9ZSBoZpHNtZBD1bHKBA"
        hostHash = b"bQv+0Xa0dByrwkA1EB0E7Xop/Fo"
        publicKey = Key.fromString(sampleKey)
        keyType = networkString(publicKey.type())
        comment = b"hello, world"

        entry = HashedEntry(hostSalt, hostHash, keyType, publicKey, comment)
        duplicate = HashedEntry(hostSalt, hostHash, keyType, publicKey, comment)

        # Vary the host salt
        self.assertNormalEqualityImplementation(
            entry,
            duplicate,
            HashedEntry(hostSalt[::-1], hostHash, keyType, publicKey, comment),
        )

        # Vary the host hash
        self.assertNormalEqualityImplementation(
            entry,
            duplicate,
            HashedEntry(hostSalt, hostHash[::-1], keyType, publicKey, comment),
        )

        # Vary the key type
        self.assertNormalEqualityImplementation(
            entry,
            duplicate,
            HashedEntry(hostSalt, hostHash, keyType[::-1], publicKey, comment),
        )

        # Vary the key
        self.assertNormalEqualityImplementation(
            entry,
            duplicate,
            HashedEntry(
                hostSalt, hostHash, keyType, Key.fromString(otherSampleKey), comment
            ),
        )

        # Vary the comment
        self.assertNormalEqualityImplementation(
            entry,
            duplicate,
            HashedEntry(hostSalt, hostHash, keyType, publicKey, comment[::-1]),
        )


class HashedEntryWithCommentTests(HashedEntryTests):
    """
    Test cases for L{PlainEntry} when parsed from a line with a comment.
    """

    hashedLine = sampleHashedLine[:-1] + b" plain text comment.\n"


class UnparsedEntryTests(TestCase, EntryTestsMixin):
    """
    Tests for L{UnparsedEntry}
    """

    def setUp(self):
        """
        Set up the 'entry' to be an unparsed entry for some random text.
        """
        self.entry = UnparsedEntry(b"    This is a bogus entry.  \n")

    def test_fromString(self):
        """
        Creating an L{UnparsedEntry} should simply record the string it was
        passed.
        """
        self.assertEqual(b"    This is a bogus entry.  \n", self.entry._string)

    def test_matchesHost(self):
        """
        An unparsed entry can't match any hosts.
        """
        self.assertFalse(self.entry.matchesHost(b"www.twistedmatrix.com"))

    def test_matchesKey(self):
        """
        An unparsed entry can't match any keys.
        """
        self.assertFalse(self.entry.matchesKey(Key.fromString(sampleKey)))

    def test_toString(self):
        """
        L{UnparsedEntry.toString} returns its input string, sans trailing
        newline.
        """
        self.assertEqual(b"    This is a bogus entry.  ", self.entry.toString())


class ParseErrorTests(TestCase):
    """
    L{HashedEntry.fromString} and L{PlainEntry.fromString} can raise a variety
    of errors depending on misformattings of certain strings.  These tests make
    sure those errors are caught.  Since many of the ways that this can go
    wrong are in the lower-level APIs being invoked by the parsing logic,
    several of these are integration tests with the C{base64} and
    L{twisted.conch.ssh.keys} modules.
    """

    def invalidEntryTest(self, cls):
        """
        If there are fewer than three elements, C{fromString} should raise
        L{InvalidEntry}.
        """
        self.assertRaises(InvalidEntry, cls.fromString, b"invalid")

    def notBase64Test(self, cls):
        """
        If the key is not base64, C{fromString} should raise L{BinasciiError}.
        """
        self.assertRaises(BinasciiError, cls.fromString, b"x x x")

    def badKeyTest(self, cls, prefix):
        """
        If the key portion of the entry is valid base64, but is not actually an
        SSH key, C{fromString} should raise L{BadKeyError}.
        """
        self.assertRaises(
            BadKeyError,
            cls.fromString,
            b" ".join(
                [prefix, b"ssh-rsa", b2a_base64(b"Hey, this isn't an SSH key!").strip()]
            ),
        )

    def test_invalidPlainEntry(self):
        """
        If there are fewer than three whitespace-separated elements in an
        entry, L{PlainEntry.fromString} should raise L{InvalidEntry}.
        """
        self.invalidEntryTest(PlainEntry)

    def test_invalidHashedEntry(self):
        """
        If there are fewer than three whitespace-separated elements in an
        entry, or the hostname salt/hash portion has more than two elements,
        L{HashedEntry.fromString} should raise L{InvalidEntry}.
        """
        self.invalidEntryTest(HashedEntry)
        a, b, c = sampleHashedLine.split()
        self.assertRaises(
            InvalidEntry, HashedEntry.fromString, b" ".join([a + b"||", b, c])
        )

    def test_plainNotBase64(self):
        """
        If the key portion of a plain entry is not decodable as base64,
        C{fromString} should raise L{BinasciiError}.
        """
        self.notBase64Test(PlainEntry)

    def test_hashedNotBase64(self):
        """
        If the key, host salt, or host hash portion of a hashed entry is not
        encoded, it will raise L{BinasciiError}.
        """
        self.notBase64Test(HashedEntry)
        a, b, c = sampleHashedLine.split()
        # Salt not valid base64.
        self.assertRaises(
            BinasciiError,
            HashedEntry.fromString,
            b" ".join([b"|1|x|" + b2a_base64(b"stuff").strip(), b, c]),
        )
        # Host hash not valid base64.
        self.assertRaises(
            BinasciiError,
            HashedEntry.fromString,
            b" ".join([HashedEntry.MAGIC + b2a_base64(b"stuff").strip() + b"|x", b, c]),
        )
        # Neither salt nor hash valid base64.
        self.assertRaises(
            BinasciiError, HashedEntry.fromString, b" ".join([b"|1|x|x", b, c])
        )

    def test_hashedBadKey(self):
        """
        If the key portion of the entry is valid base64, but is not actually an
        SSH key, C{HashedEntry.fromString} should raise L{BadKeyError}.
        """
        a, b, c = sampleHashedLine.split()
        self.badKeyTest(HashedEntry, a)

    def test_plainBadKey(self):
        """
        If the key portion of the entry is valid base64, but is not actually an
        SSH key, C{PlainEntry.fromString} should raise L{BadKeyError}.
        """
        self.badKeyTest(PlainEntry, b"hostname")


class KnownHostsDatabaseTests(TestCase):
    """
    Tests for L{KnownHostsFile}.
    """

    def pathWithContent(self, content):
        """
        Return a FilePath with the given initial content.
        """
        fp = FilePath(self.mktemp())
        fp.setContent(content)
        return fp

    def loadSampleHostsFile(
        self,
        content=(
            sampleHashedLine
            + otherSamplePlaintextLine
            + b"\n# That was a blank line.\n"
            b"This is just unparseable.\n"
            b"|1|This also unparseable.\n"
        ),
    ):
        """
        Return a sample hosts file, with keys for www.twistedmatrix.com and
        divmod.com present.
        """
        return KnownHostsFile.fromPath(self.pathWithContent(content))

    def test_readOnlySavePath(self):
        """
        L{KnownHostsFile.savePath} is read-only; if an assignment is made to
        it, L{AttributeError} is raised and the value is unchanged.
        """
        path = FilePath(self.mktemp())
        new = FilePath(self.mktemp())
        hostsFile = KnownHostsFile(path)
        self.assertRaises(AttributeError, setattr, hostsFile, "savePath", new)
        self.assertEqual(path, hostsFile.savePath)

    def test_defaultInitializerIgnoresExisting(self):
        """
        The default initializer for L{KnownHostsFile} disregards any existing
        contents in the save path.
        """
        hostsFile = KnownHostsFile(self.pathWithContent(sampleHashedLine))
        self.assertEqual([], list(hostsFile.iterentries()))

    def test_defaultInitializerClobbersExisting(self):
        """
        After using the default initializer for L{KnownHostsFile}, the first use
        of L{KnownHostsFile.save} overwrites any existing contents in the save
        path.
        """
        path = self.pathWithContent(sampleHashedLine)
        hostsFile = KnownHostsFile(path)
        entry = hostsFile.addHostKey(b"www.example.com", Key.fromString(otherSampleKey))
        hostsFile.save()
        # Check KnownHostsFile to see what it thinks the state is
        self.assertEqual([entry], list(hostsFile.iterentries()))
        # And also directly check the underlying file itself
        self.assertEqual(entry.toString() + b"\n", path.getContent())

    def test_saveResetsClobberState(self):
        """
        After L{KnownHostsFile.save} is used once with an instance initialized
        by the default initializer, contents of the save path are respected and
        preserved.
        """
        hostsFile = KnownHostsFile(self.pathWithContent(sampleHashedLine))
        preSave = hostsFile.addHostKey(
            b"www.example.com", Key.fromString(otherSampleKey)
        )
        hostsFile.save()
        postSave = hostsFile.addHostKey(
            b"another.example.com", Key.fromString(thirdSampleKey)
        )
        hostsFile.save()

        self.assertEqual([preSave, postSave], list(hostsFile.iterentries()))

    def test_loadFromPath(self):
        """
        Loading a L{KnownHostsFile} from a path with six entries in it will
        result in a L{KnownHostsFile} object with six L{IKnownHostEntry}
        providers in it.
        """
        hostsFile = self.loadSampleHostsFile()
        self.assertEqual(6, len(list(hostsFile.iterentries())))

    def test_iterentriesUnsaved(self):
        """
        If the save path for a L{KnownHostsFile} does not exist,
        L{KnownHostsFile.iterentries} still returns added but unsaved entries.
        """
        hostsFile = KnownHostsFile(FilePath(self.mktemp()))
        hostsFile.addHostKey(b"www.example.com", Key.fromString(sampleKey))
        self.assertEqual(1, len(list(hostsFile.iterentries())))

    def test_verifyHashedEntry(self):
        """
        Loading a L{KnownHostsFile} from a path containing a single valid
        L{HashedEntry} entry will result in a L{KnownHostsFile} object
        with one L{IKnownHostEntry} provider.
        """
        hostsFile = self.loadSampleHostsFile(sampleHashedLine)
        entries = list(hostsFile.iterentries())
        self.assertIsInstance(entries[0], HashedEntry)
        self.assertTrue(entries[0].matchesHost(b"www.twistedmatrix.com"))
        self.assertEqual(1, len(entries))

    def test_verifyPlainEntry(self):
        """
        Loading a L{KnownHostsFile} from a path containing a single valid
        L{PlainEntry} entry will result in a L{KnownHostsFile} object
        with one L{IKnownHostEntry} provider.
        """
        hostsFile = self.loadSampleHostsFile(otherSamplePlaintextLine)
        entries = list(hostsFile.iterentries())
        self.assertIsInstance(entries[0], PlainEntry)
        self.assertTrue(entries[0].matchesHost(b"divmod.com"))
        self.assertEqual(1, len(entries))

    def test_verifyUnparsedEntry(self):
        """
        Loading a L{KnownHostsFile} from a path that only contains '\n' will
        result in a L{KnownHostsFile} object containing a L{UnparsedEntry}
        object.
        """
        hostsFile = self.loadSampleHostsFile(b"\n")
        entries = list(hostsFile.iterentries())
        self.assertIsInstance(entries[0], UnparsedEntry)
        self.assertEqual(entries[0].toString(), b"")
        self.assertEqual(1, len(entries))

    def test_verifyUnparsedComment(self):
        """
        Loading a L{KnownHostsFile} from a path that contains a comment will
        result in a L{KnownHostsFile} object containing a L{UnparsedEntry}
        object.
        """
        hostsFile = self.loadSampleHostsFile(b"# That was a blank line.\n")
        entries = list(hostsFile.iterentries())
        self.assertIsInstance(entries[0], UnparsedEntry)
        self.assertEqual(entries[0].toString(), b"# That was a blank line.")

    def test_verifyUnparsableLine(self):
        """
        Loading a L{KnownHostsFile} from a path that contains an unparseable
        line will be represented as an L{UnparsedEntry} instance.
        """
        hostsFile = self.loadSampleHostsFile(b"This is just unparseable.\n")
        entries = list(hostsFile.iterentries())
        self.assertIsInstance(entries[0], UnparsedEntry)
        self.assertEqual(entries[0].toString(), b"This is just unparseable.")
        self.assertEqual(1, len(entries))

    def test_verifyUnparsableEncryptionMarker(self):
        """
        Loading a L{KnownHostsFile} from a path containing an unparseable line
        that starts with an encryption marker will be represented as an
        L{UnparsedEntry} instance.
        """
        hostsFile = self.loadSampleHostsFile(b"|1|This is unparseable.\n")
        entries = list(hostsFile.iterentries())
        self.assertIsInstance(entries[0], UnparsedEntry)
        self.assertEqual(entries[0].toString(), b"|1|This is unparseable.")
        self.assertEqual(1, len(entries))

    def test_loadNonExistent(self):
        """
        Loading a L{KnownHostsFile} from a path that does not exist should
        result in an empty L{KnownHostsFile} that will save back to that path.
        """
        pn = self.mktemp()
        knownHostsFile = KnownHostsFile.fromPath(FilePath(pn))
        entries = list(knownHostsFile.iterentries())
        self.assertEqual([], entries)
        self.assertFalse(FilePath(pn).exists())
        knownHostsFile.save()
        self.assertTrue(FilePath(pn).exists())

    def test_loadNonExistentParent(self):
        """
        Loading a L{KnownHostsFile} from a path whose parent directory does not
        exist should result in an empty L{KnownHostsFile} that will save back
        to that path, creating its parent directory(ies) in the process.
        """
        thePath = FilePath(self.mktemp())
        knownHostsPath = thePath.child("foo").child(b"known_hosts")
        knownHostsFile = KnownHostsFile.fromPath(knownHostsPath)
        knownHostsFile.save()
        knownHostsPath.restat(False)
        self.assertTrue(knownHostsPath.exists())

    def test_savingAddsEntry(self):
        """
        L{KnownHostsFile.save} will write out a new file with any entries
        that have been added.
        """
        path = self.pathWithContent(sampleHashedLine + otherSamplePlaintextLine)
        knownHostsFile = KnownHostsFile.fromPath(path)
        newEntry = knownHostsFile.addHostKey(
            b"some.example.com", Key.fromString(thirdSampleKey)
        )
        expectedContent = (
            sampleHashedLine
            + otherSamplePlaintextLine
            + HashedEntry.MAGIC
            + b2a_base64(newEntry._hostSalt).strip()
            + b"|"
            + b2a_base64(newEntry._hostHash).strip()
            + b" ssh-rsa "
            + thirdSampleEncodedKey
            + b"\n"
        )

        # Sanity check, let's make sure the base64 API being used for the test
        # isn't inserting spurious newlines.
        self.assertEqual(3, expectedContent.count(b"\n"))
        knownHostsFile.save()
        self.assertEqual(expectedContent, path.getContent())

    def test_savingAvoidsDuplication(self):
        """
        L{KnownHostsFile.save} only writes new entries to the save path, not
        entries which were added and already written by a previous call to
        C{save}.
        """
        path = FilePath(self.mktemp())
        knownHosts = KnownHostsFile(path)
        entry = knownHosts.addHostKey(b"some.example.com", Key.fromString(sampleKey))
        knownHosts.save()
        knownHosts.save()

        knownHosts = KnownHostsFile.fromPath(path)
        self.assertEqual([entry], list(knownHosts.iterentries()))

    def test_savingsPreservesExisting(self):
        """
        L{KnownHostsFile.save} will not overwrite existing entries in its save
        path, even if they were only added after the L{KnownHostsFile} instance
        was initialized.
        """
        # Start off with one host/key pair in the file
        path = self.pathWithContent(sampleHashedLine)
        knownHosts = KnownHostsFile.fromPath(path)

        # After initializing the KnownHostsFile instance, add a second host/key
        # pair to the file directly - without the instance's help or knowledge.
        with path.open("a") as hostsFileObj:
            hostsFileObj.write(otherSamplePlaintextLine)

        # Add a third host/key pair using the KnownHostsFile instance
        key = Key.fromString(thirdSampleKey)
        knownHosts.addHostKey(b"brandnew.example.com", key)
        knownHosts.save()

        # Check that all three host/key pairs are present.
        knownHosts = KnownHostsFile.fromPath(path)
        self.assertEqual(
            [True, True, True],
            [
                knownHosts.hasHostKey(
                    b"www.twistedmatrix.com", Key.fromString(sampleKey)
                ),
                knownHosts.hasHostKey(b"divmod.com", Key.fromString(otherSampleKey)),
                knownHosts.hasHostKey(b"brandnew.example.com", key),
            ],
        )

    def test_hasPresentKey(self):
        """
        L{KnownHostsFile.hasHostKey} returns C{True} when a key for the given
        hostname is present and matches the expected key.
        """
        hostsFile = self.loadSampleHostsFile()
        self.assertTrue(
            hostsFile.hasHostKey(b"www.twistedmatrix.com", Key.fromString(sampleKey))
        )

    def test_notPresentKey(self):
        """
        L{KnownHostsFile.hasHostKey} returns C{False} when a key for the given
        hostname is not present.
        """
        hostsFile = self.loadSampleHostsFile()
        self.assertFalse(
            hostsFile.hasHostKey(b"non-existent.example.com", Key.fromString(sampleKey))
        )
        self.assertTrue(
            hostsFile.hasHostKey(b"www.twistedmatrix.com", Key.fromString(sampleKey))
        )
        self.assertFalse(
            hostsFile.hasHostKey(
                b"www.twistedmatrix.com", Key.fromString(ecdsaSampleKey)
            )
        )

    def test_hasLaterAddedKey(self):
        """
        L{KnownHostsFile.hasHostKey} returns C{True} when a key for the given
        hostname is present in the file, even if it is only added to the file
        after the L{KnownHostsFile} instance is initialized.
        """
        key = Key.fromString(sampleKey)
        entry = PlainEntry([b"brandnew.example.com"], key.sshType(), key, b"")
        hostsFile = self.loadSampleHostsFile()
        with hostsFile.savePath.open("a") as hostsFileObj:
            hostsFileObj.write(entry.toString() + b"\n")
        self.assertEqual(True, hostsFile.hasHostKey(b"brandnew.example.com", key))

    def test_savedEntryHasKeyMismatch(self):
        """
        L{KnownHostsFile.hasHostKey} raises L{HostKeyChanged} if the host key is
        present in the underlying file, but different from the expected one.
        The resulting exception should have an C{offendingEntry} indicating the
        given entry.
        """
        hostsFile = self.loadSampleHostsFile()
        entries = list(hostsFile.iterentries())
        exception = self.assertRaises(
            HostKeyChanged,
            hostsFile.hasHostKey,
            b"www.twistedmatrix.com",
            Key.fromString(otherSampleKey),
        )
        self.assertEqual(exception.offendingEntry, entries[0])
        self.assertEqual(exception.lineno, 1)
        self.assertEqual(exception.path, hostsFile.savePath)

    def test_savedEntryAfterAddHasKeyMismatch(self):
        """
        Even after a new entry has been added in memory but not yet saved, the
        L{HostKeyChanged} exception raised by L{KnownHostsFile.hasHostKey} has a
        C{lineno} attribute which indicates the 1-based line number of the
        offending entry in the underlying file when the given host key does not
        match the expected host key.
        """
        hostsFile = self.loadSampleHostsFile()
        hostsFile.addHostKey(b"www.example.com", Key.fromString(otherSampleKey))
        exception = self.assertRaises(
            HostKeyChanged,
            hostsFile.hasHostKey,
            b"www.twistedmatrix.com",
            Key.fromString(otherSampleKey),
        )
        self.assertEqual(exception.lineno, 1)
        self.assertEqual(exception.path, hostsFile.savePath)

    def test_unsavedEntryHasKeyMismatch(self):
        """
        L{KnownHostsFile.hasHostKey} raises L{HostKeyChanged} if the host key is
        present in memory (but not yet saved), but different from the expected
        one.  The resulting exception has a C{offendingEntry} indicating the
        given entry, but no filename or line number information (reflecting the
        fact that the entry exists only in memory).
        """
        hostsFile = KnownHostsFile(FilePath(self.mktemp()))
        entry = hostsFile.addHostKey(b"www.example.com", Key.fromString(otherSampleKey))
        exception = self.assertRaises(
            HostKeyChanged,
            hostsFile.hasHostKey,
            b"www.example.com",
            Key.fromString(thirdSampleKey),
        )
        self.assertEqual(exception.offendingEntry, entry)
        self.assertIsNone(exception.lineno)
        self.assertIsNone(exception.path)

    def test_addHostKey(self):
        """
        L{KnownHostsFile.addHostKey} adds a new L{HashedEntry} to the host
        file, and returns it.
        """
        hostsFile = self.loadSampleHostsFile()
        aKey = Key.fromString(thirdSampleKey)
        self.assertEqual(False, hostsFile.hasHostKey(b"somewhere.example.com", aKey))
        newEntry = hostsFile.addHostKey(b"somewhere.example.com", aKey)

        # The code in OpenSSH requires host salts to be 20 characters long.
        # This is the required length of a SHA-1 HMAC hash, so it's just a
        # sanity check.
        self.assertEqual(20, len(newEntry._hostSalt))
        self.assertEqual(True, newEntry.matchesHost(b"somewhere.example.com"))
        self.assertEqual(newEntry.keyType, b"ssh-rsa")
        self.assertEqual(aKey, newEntry.publicKey)
        self.assertEqual(True, hostsFile.hasHostKey(b"somewhere.example.com", aKey))

    def test_randomSalts(self):
        """
        L{KnownHostsFile.addHostKey} generates a random salt for each new key,
        so subsequent salts will be different.
        """
        hostsFile = self.loadSampleHostsFile()
        aKey = Key.fromString(thirdSampleKey)
        self.assertNotEqual(
            hostsFile.addHostKey(b"somewhere.example.com", aKey)._hostSalt,
            hostsFile.addHostKey(b"somewhere-else.example.com", aKey)._hostSalt,
        )

    def test_verifyValidKey(self):
        """
        Verifying a valid key should return a L{Deferred} which fires with
        True.
        """
        hostsFile = self.loadSampleHostsFile()
        hostsFile.addHostKey(b"1.2.3.4", Key.fromString(sampleKey))
        ui = FakeUI()
        d = hostsFile.verifyHostKey(
            ui, b"www.twistedmatrix.com", b"1.2.3.4", Key.fromString(sampleKey)
        )
        l = []
        d.addCallback(l.append)
        self.assertEqual(l, [True])

    def test_verifyInvalidKey(self):
        """
        Verifying an invalid key should return a L{Deferred} which fires with a
        L{HostKeyChanged} failure.
        """
        hostsFile = self.loadSampleHostsFile()
        wrongKey = Key.fromString(thirdSampleKey)
        ui = FakeUI()
        hostsFile.addHostKey(b"1.2.3.4", Key.fromString(sampleKey))
        d = hostsFile.verifyHostKey(ui, b"www.twistedmatrix.com", b"1.2.3.4", wrongKey)
        return self.assertFailure(d, HostKeyChanged)

    def verifyNonPresentKey(self):
        """
        Set up a test to verify a key that isn't present.  Return a 3-tuple of
        the UI, a list set up to collect the result of the verifyHostKey call,
        and the sample L{KnownHostsFile} being used.

        This utility method avoids returning a L{Deferred}, and records results
        in the returned list instead, because the events which get generated
        here are pre-recorded in the 'ui' object.  If the L{Deferred} in
        question does not fire, the it will fail quickly with an empty list.
        """
        hostsFile = self.loadSampleHostsFile()
        absentKey = Key.fromString(thirdSampleKey)
        ui = FakeUI()
        l = []
        d = hostsFile.verifyHostKey(
            ui, b"sample-host.example.com", b"4.3.2.1", absentKey
        )
        d.addBoth(l.append)
        self.assertEqual([], l)
        self.assertEqual(
            ui.promptText,
            b"The authenticity of host 'sample-host.example.com (4.3.2.1)' "
            b"can't be established.\n"
            b"RSA key fingerprint is "
            b"SHA256:mS7mDBGhewdzJkaKRkx+wMjUdZb/GzvgcdoYjX5Js9I=.\n"
            b"Are you sure you want to continue connecting (yes/no)? ",
        )
        return ui, l, hostsFile

    def test_verifyNonPresentKey_Yes(self):
        """
        Verifying a key where neither the hostname nor the IP are present
        should result in the UI being prompted with a message explaining as
        much.  If the UI says yes, the Deferred should fire with True.
        """
        ui, l, knownHostsFile = self.verifyNonPresentKey()
        ui.promptDeferred.callback(True)
        self.assertEqual([True], l)
        reloaded = KnownHostsFile.fromPath(knownHostsFile.savePath)
        self.assertEqual(
            True, reloaded.hasHostKey(b"4.3.2.1", Key.fromString(thirdSampleKey))
        )
        self.assertEqual(
            True,
            reloaded.hasHostKey(
                b"sample-host.example.com", Key.fromString(thirdSampleKey)
            ),
        )

    def test_verifyNonPresentKey_No(self):
        """
        Verifying a key where neither the hostname nor the IP are present
        should result in the UI being prompted with a message explaining as
        much.  If the UI says no, the Deferred should fail with
        UserRejectedKey.
        """
        ui, l, knownHostsFile = self.verifyNonPresentKey()
        ui.promptDeferred.callback(False)
        l[0].trap(UserRejectedKey)

    def test_verifyNonPresentECKey(self):
        """
        Set up a test to verify an ECDSA key that isn't present.
        Return a 3-tuple of the UI, a list set up to collect the result
        of the verifyHostKey call, and the sample L{KnownHostsFile} being used.
        """
        ecObj = Key._fromECComponents(
            x=keydata.ECDatanistp256["x"],
            y=keydata.ECDatanistp256["y"],
            privateValue=keydata.ECDatanistp256["privateValue"],
            curve=keydata.ECDatanistp256["curve"],
        )

        hostsFile = self.loadSampleHostsFile()
        ui = FakeUI()
        l = []
        d = hostsFile.verifyHostKey(ui, b"sample-host.example.com", b"4.3.2.1", ecObj)
        d.addBoth(l.append)
        self.assertEqual([], l)
        self.assertEqual(
            ui.promptText,
            b"The authenticity of host 'sample-host.example.com (4.3.2.1)' "
            b"can't be established.\n"
            b"ECDSA key fingerprint is "
            b"SHA256:fJnSpgCcYoYYsaBbnWj1YBghGh/QTDgfe4w4U5M5tEo=.\n"
            b"Are you sure you want to continue connecting (yes/no)? ",
        )

    def test_verifyHostIPMismatch(self):
        """
        Verifying a key where the host is present (and correct), but the IP is
        present and different, should result the deferred firing in a
        HostKeyChanged failure.
        """
        hostsFile = self.loadSampleHostsFile()
        wrongKey = Key.fromString(thirdSampleKey)
        ui = FakeUI()
        d = hostsFile.verifyHostKey(ui, b"www.twistedmatrix.com", b"4.3.2.1", wrongKey)
        return self.assertFailure(d, HostKeyChanged)

    def test_verifyKeyForHostAndIP(self):
        """
        Verifying a key where the hostname is present but the IP is not should
        result in the key being added for the IP and the user being warned
        about the change.
        """
        ui = FakeUI()
        hostsFile = self.loadSampleHostsFile()
        expectedKey = Key.fromString(sampleKey)
        hostsFile.verifyHostKey(ui, b"www.twistedmatrix.com", b"5.4.3.2", expectedKey)
        self.assertEqual(
            True,
            KnownHostsFile.fromPath(hostsFile.savePath).hasHostKey(
                b"5.4.3.2", expectedKey
            ),
        )
        self.assertEqual(
            [
                "Warning: Permanently added the RSA host key for IP address "
                "'5.4.3.2' to the list of known hosts."
            ],
            ui.userWarnings,
        )

    def test_getHostKeyAlgorithms(self):
        """
        For a given host, get the host key algorithms for that
        host in the known_hosts file.
        """
        hostsFile = self.loadSampleHostsFile()
        hostsFile.addHostKey(b"www.twistedmatrix.com", Key.fromString(otherSampleKey))
        hostsFile.addHostKey(b"www.twistedmatrix.com", Key.fromString(ecdsaSampleKey))
        hostsFile.save()
        options = {}
        options["known-hosts"] = hostsFile.savePath.path
        algorithms = default.getHostKeyAlgorithms(b"www.twistedmatrix.com", options)
        expectedAlgorithms = [b"ssh-rsa", b"ecdsa-sha2-nistp256"]
        self.assertEqual(algorithms, expectedAlgorithms)


class FakeFile:
    """
    A fake file-like object that acts enough like a file for
    L{ConsoleUI.prompt}.
    """

    def __init__(self):
        self.inlines = []
        self.outchunks = []
        self.closed = False

    def readline(self):
        """
        Return a line from the 'inlines' list.
        """
        return self.inlines.pop(0)

    def write(self, chunk):
        """
        Append the given item to the 'outchunks' list.
        """
        if self.closed:
            raise OSError("the file was closed")
        self.outchunks.append(chunk)

    def close(self):
        """
        Set the 'closed' flag to True, explicitly marking that it has been
        closed.
        """
        self.closed = True


class ConsoleUITests(TestCase):
    """
    Test cases for L{ConsoleUI}.
    """

    def setUp(self):
        """
        Create a L{ConsoleUI} pointed at a L{FakeFile}.
        """
        self.fakeFile = FakeFile()
        self.ui = ConsoleUI(self.openFile)

    def openFile(self):
        """
        Return the current fake file.
        """
        return self.fakeFile

    def newFile(self, lines):
        """
        Create a new fake file (the next file that self.ui will open) with the
        given list of lines to be returned from readline().
        """
        self.fakeFile = FakeFile()
        self.fakeFile.inlines = lines

    def test_promptYes(self):
        """
        L{ConsoleUI.prompt} writes a message to the console, then reads a line.
        If that line is 'yes', then it returns a L{Deferred} that fires with
        True.
        """
        for okYes in [b"yes", b"Yes", b"yes\n"]:
            self.newFile([okYes])
            l = []
            self.ui.prompt("Hello, world!").addCallback(l.append)
            self.assertEqual(["Hello, world!"], self.fakeFile.outchunks)
            self.assertEqual([True], l)
            self.assertTrue(self.fakeFile.closed)

    def test_promptNo(self):
        """
        L{ConsoleUI.prompt} writes a message to the console, then reads a line.
        If that line is 'no', then it returns a L{Deferred} that fires with
        False.
        """
        for okNo in [b"no", b"No", b"no\n"]:
            self.newFile([okNo])
            l = []
            self.ui.prompt("Goodbye, world!").addCallback(l.append)
            self.assertEqual(["Goodbye, world!"], self.fakeFile.outchunks)
            self.assertEqual([False], l)
            self.assertTrue(self.fakeFile.closed)

    def test_promptRepeatedly(self):
        """
        L{ConsoleUI.prompt} writes a message to the console, then reads a line.
        If that line is neither 'yes' nor 'no', then it says "Please enter
        'yes' or 'no'" until it gets a 'yes' or a 'no', at which point it
        returns a Deferred that answers either True or False.
        """
        self.newFile([b"what", b"uh", b"okay", b"yes"])
        l = []
        self.ui.prompt(b"Please say something useful.").addCallback(l.append)
        self.assertEqual([True], l)
        self.assertEqual(
            self.fakeFile.outchunks,
            [b"Please say something useful."] + [b"Please type 'yes' or 'no': "] * 3,
        )
        self.assertTrue(self.fakeFile.closed)
        self.newFile([b"blah", b"stuff", b"feh", b"no"])
        l = []
        self.ui.prompt(b"Please say something negative.").addCallback(l.append)
        self.assertEqual([False], l)
        self.assertEqual(
            self.fakeFile.outchunks,
            [b"Please say something negative."] + [b"Please type 'yes' or 'no': "] * 3,
        )
        self.assertTrue(self.fakeFile.closed)

    def test_promptOpenFailed(self):
        """
        If the C{opener} passed to L{ConsoleUI} raises an exception, that
        exception will fail the L{Deferred} returned from L{ConsoleUI.prompt}.
        """

        def raiseIt():
            raise OSError()

        ui = ConsoleUI(raiseIt)
        d = ui.prompt("This is a test.")
        return self.assertFailure(d, IOError)

    def test_warn(self):
        """
        L{ConsoleUI.warn} should output a message to the console object.
        """
        self.ui.warn("Test message.")
        self.assertEqual(["Test message."], self.fakeFile.outchunks)
        self.assertTrue(self.fakeFile.closed)

    def test_warnOpenFailed(self):
        """
        L{ConsoleUI.warn} should log a traceback if the output can't be opened.
        """

        def raiseIt():
            1 / 0

        ui = ConsoleUI(raiseIt)
        ui.warn("This message never makes it.")
        self.assertEqual(len(self.flushLoggedErrors(ZeroDivisionError)), 1)


class FakeUI:
    """
    A fake UI object, adhering to the interface expected by
    L{KnownHostsFile.verifyHostKey}

    @ivar userWarnings: inputs provided to 'warn'.

    @ivar promptDeferred: last result returned from 'prompt'.

    @ivar promptText: the last input provided to 'prompt'.
    """

    def __init__(self):
        self.userWarnings = []
        self.promptDeferred = None
        self.promptText = None

    def prompt(self, text):
        """
        Issue the user an interactive prompt, which they can accept or deny.
        """
        self.promptText = text
        self.promptDeferred = Deferred()
        return self.promptDeferred

    def warn(self, text):
        """
        Issue a non-interactive warning to the user.
        """
        self.userWarnings.append(text)


class FakeObject:
    """
    A fake object that can have some attributes.  Used to fake
    L{SSHClientTransport} and L{SSHClientFactory}.
    """


@skipIf(not FilePath("/dev/tty").exists(), "Platform lacks /dev/tty")
class DefaultAPITests(TestCase):
    """
    The API in L{twisted.conch.client.default.verifyHostKey} is the integration
    point between the code in the rest of conch and L{KnownHostsFile}.
    """

    def patchedOpen(self, fname, mode, **kwargs):
        """
        The patched version of 'open'; this returns a L{FakeFile} that the
        instantiated L{ConsoleUI} can use.
        """
        self.assertEqual(fname, "/dev/tty")
        self.assertEqual(mode, "r+b")
        self.assertEqual(kwargs["buffering"], 0)
        return self.fakeFile

    def setUp(self):
        """
        Patch 'open' in verifyHostKey.
        """
        self.fakeFile = FakeFile()
        self.patch(default, "_open", self.patchedOpen)
        self.hostsOption = self.mktemp()
        self.hashedEntries = {}
        knownHostsFile = KnownHostsFile(FilePath(self.hostsOption))
        for host in (b"exists.example.com", b"4.3.2.1"):
            entry = knownHostsFile.addHostKey(host, Key.fromString(sampleKey))
            self.hashedEntries[host] = entry
        knownHostsFile.save()
        self.fakeTransport = FakeObject()
        self.fakeTransport.factory = FakeObject()
        self.options = self.fakeTransport.factory.options = {
            "host": b"exists.example.com",
            "known-hosts": self.hostsOption,
        }

    def test_verifyOKKey(self):
        """
        L{default.verifyHostKey} should return a L{Deferred} which fires with
        C{1} when passed a host, IP, and key which already match the
        known_hosts file it is supposed to check.
        """
        l = []
        default.verifyHostKey(
            self.fakeTransport, b"4.3.2.1", sampleKey, b"I don't care."
        ).addCallback(l.append)
        self.assertEqual([1], l)

    def replaceHome(self, tempHome):
        """
        Replace the HOME environment variable until the end of the current
        test, with the given new home-directory, so that L{os.path.expanduser}
        will yield controllable, predictable results.

        @param tempHome: the pathname to replace the HOME variable with.

        @type tempHome: L{str}
        """
        oldHome = os.environ.get("HOME")

        def cleanupHome():
            if oldHome is None:
                del os.environ["HOME"]
            else:
                os.environ["HOME"] = oldHome

        self.addCleanup(cleanupHome)
        os.environ["HOME"] = tempHome

    def test_noKnownHostsOption(self):
        """
        L{default.verifyHostKey} should find your known_hosts file in
        ~/.ssh/known_hosts if you don't specify one explicitly on the command
        line.
        """
        l = []
        tmpdir = self.mktemp()
        oldHostsOption = self.hostsOption
        hostsNonOption = FilePath(tmpdir).child(".ssh").child("known_hosts")
        hostsNonOption.parent().makedirs()
        FilePath(oldHostsOption).moveTo(hostsNonOption)
        self.replaceHome(tmpdir)
        self.options["known-hosts"] = None
        default.verifyHostKey(
            self.fakeTransport, b"4.3.2.1", sampleKey, b"I don't care."
        ).addCallback(l.append)
        self.assertEqual([1], l)

    def test_verifyHostButNotIP(self):
        """
        L{default.verifyHostKey} should return a L{Deferred} which fires with
        C{1} when passed a host which matches with an IP is not present in its
        known_hosts file, and should also warn the user that it has added the
        IP address.
        """
        l = []
        default.verifyHostKey(
            self.fakeTransport, b"8.7.6.5", sampleKey, b"Fingerprint not required."
        ).addCallback(l.append)
        self.assertEqual(
            [
                "Warning: Permanently added the RSA host key for IP address "
                "'8.7.6.5' to the list of known hosts."
            ],
            self.fakeFile.outchunks,
        )
        self.assertEqual([1], l)
        knownHostsFile = KnownHostsFile.fromPath(FilePath(self.hostsOption))
        self.assertTrue(
            knownHostsFile.hasHostKey(b"8.7.6.5", Key.fromString(sampleKey))
        )

    def test_verifyQuestion(self):
        """
        L{default.verifyHostKey} should return a L{Default} which fires with
        C{0} when passed an unknown host that the user refuses to acknowledge.
        """
        self.fakeTransport.factory.options["host"] = b"fake.example.com"
        self.fakeFile.inlines.append(b"no")
        d = default.verifyHostKey(
            self.fakeTransport, b"9.8.7.6", otherSampleKey, b"No fingerprint!"
        )
        self.assertEqual(
            [
                b"The authenticity of host 'fake.example.com (9.8.7.6)' "
                b"can't be established.\n"
                b"RSA key fingerprint is "
                b"SHA256:vD0YydsNIUYJa7yLZl3tIL8h0vZvQ8G+HPG7JLmQV0s=.\n"
                b"Are you sure you want to continue connecting (yes/no)? "
            ],
            self.fakeFile.outchunks,
        )
        return self.assertFailure(d, UserRejectedKey)

    def test_verifyBadKey(self):
        """
        L{default.verifyHostKey} should return a L{Deferred} which fails with
        L{HostKeyChanged} if the host key is incorrect.
        """
        d = default.verifyHostKey(
            self.fakeTransport, b"4.3.2.1", otherSampleKey, "Again, not required."
        )
        return self.assertFailure(d, HostKeyChanged)

    def test_inKnownHosts(self):
        """
        L{default.isInKnownHosts} should return C{1} when a host with a key
        is in the known hosts file.
        """
        host = self.hashedEntries[b"4.3.2.1"].toString().split()[0]
        r = default.isInKnownHosts(
            host,
            Key.fromString(sampleKey).blob(),
            {"known-hosts": FilePath(self.hostsOption).path},
        )
        self.assertEqual(1, r)

    def test_notInKnownHosts(self):
        """
        L{default.isInKnownHosts} should return C{0} when a host with a key
        is not in the known hosts file.
        """
        r = default.isInKnownHosts(
            "not.there", b"irrelevant", {"known-hosts": FilePath(self.hostsOption).path}
        )
        self.assertEqual(0, r)

    def test_inKnownHostsKeyChanged(self):
        """
        L{default.isInKnownHosts} should return C{2} when a host with a key
        other than the given one is in the known hosts file.
        """
        host = self.hashedEntries[b"4.3.2.1"].toString().split()[0]
        r = default.isInKnownHosts(
            host,
            Key.fromString(otherSampleKey).blob(),
            {"known-hosts": FilePath(self.hostsOption).path},
        )
        self.assertEqual(2, r)
