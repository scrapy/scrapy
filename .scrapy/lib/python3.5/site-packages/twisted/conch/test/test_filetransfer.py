# -*- test-case-name: twisted.conch.test.test_filetransfer -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE file for details.

"""
Tests for L{twisted.conch.ssh.filetransfer}.
"""

from __future__ import division, absolute_import

import os
import re
import struct

from twisted.trial import unittest
try:
    from twisted.conch import unix
    unix # shut up pyflakes
except ImportError:
    unix = None

from twisted.conch import avatar
from twisted.conch.ssh import common, connection, filetransfer, session
from twisted.internet import defer
from twisted.protocols import loopback
from twisted.python import components
from twisted.python.compat import long, networkString


class TestAvatar(avatar.ConchUser):
    def __init__(self):
        avatar.ConchUser.__init__(self)
        self.channelLookup[b'session'] = session.SSHSession
        self.subsystemLookup[b'sftp'] = filetransfer.FileTransferServer

    def _runAsUser(self, f, *args, **kw):
        try:
            f = iter(f)
        except TypeError:
            f = [(f, args, kw)]
        for i in f:
            func = i[0]
            args = len(i)>1 and i[1] or ()
            kw = len(i)>2 and i[2] or {}
            r = func(*args, **kw)
        return r


class FileTransferTestAvatar(TestAvatar):

    def __init__(self, homeDir):
        TestAvatar.__init__(self)
        self.homeDir = homeDir

    def getHomeDir(self):
        return os.path.join(networkString(os.getcwd()), self.homeDir)


class ConchSessionForTestAvatar:

    def __init__(self, avatar):
        self.avatar = avatar

if unix:
    if not hasattr(unix, 'SFTPServerForUnixConchUser'):
        # unix should either be a fully working module, or None.  I'm not sure
        # how this happens, but on win32 it does.  Try to cope.  --spiv.
        import warnings
        warnings.warn(("twisted.conch.unix imported %r, "
                       "but doesn't define SFTPServerForUnixConchUser'")
                      % (unix,))
        unix = None
    else:
        class FileTransferForTestAvatar(unix.SFTPServerForUnixConchUser):

            def gotVersion(self, version, otherExt):
                return {b'conchTest' : b'ext data'}

            def extendedRequest(self, extName, extData):
                if extName == b'testExtendedRequest':
                    return b'bar'
                raise NotImplementedError

        components.registerAdapter(FileTransferForTestAvatar,
                                   TestAvatar,
                                   filetransfer.ISFTPServer)

class SFTPTestBase(unittest.TestCase):

    def setUp(self):
        self.testDir = networkString(self.mktemp())
        # Give the testDir another level so we can safely "cd .." from it in
        # tests.
        self.testDir = os.path.join(self.testDir, b'extra')
        os.makedirs(os.path.join(self.testDir, b'testDirectory'))

        with open(os.path.join(self.testDir, b'testfile1'), 'wb') as f:
            f.write(b'a'*10+b'b'*10)
            with open('/dev/urandom', 'rb') as f2:
                f.write(f2.read(1024*64)) # random data
        os.chmod(os.path.join(self.testDir, b'testfile1'), 0o644)
        with open(os.path.join(self.testDir, b'testRemoveFile'), 'wb') as f:
            f.write(b'a')
        with open(os.path.join(self.testDir, b'testRenameFile'), 'wb') as f:
            f.write(b'a')
        with open(os.path.join(self.testDir, b'.testHiddenFile'), 'wb') as f:
            f.write(b'a')


class OurServerOurClientTests(SFTPTestBase):

    if not unix:
        skip = "can't run on non-posix computers"

    def setUp(self):
        SFTPTestBase.setUp(self)

        self.avatar = FileTransferTestAvatar(self.testDir)
        self.server = filetransfer.FileTransferServer(avatar=self.avatar)
        clientTransport = loopback.LoopbackRelay(self.server)

        self.client = filetransfer.FileTransferClient()
        self._serverVersion = None
        self._extData = None
        def _(serverVersion, extData):
            self._serverVersion = serverVersion
            self._extData = extData
        self.client.gotServerVersion = _
        serverTransport = loopback.LoopbackRelay(self.client)
        self.client.makeConnection(clientTransport)
        self.server.makeConnection(serverTransport)

        self.clientTransport = clientTransport
        self.serverTransport = serverTransport

        self._emptyBuffers()


    def _emptyBuffers(self):
        while self.serverTransport.buffer or self.clientTransport.buffer:
            self.serverTransport.clearBuffer()
            self.clientTransport.clearBuffer()


    def tearDown(self):
        self.serverTransport.loseConnection()
        self.clientTransport.loseConnection()
        self.serverTransport.clearBuffer()
        self.clientTransport.clearBuffer()


    def testServerVersion(self):
        self.assertEqual(self._serverVersion, 3)
        self.assertEqual(self._extData, {b'conchTest' : b'ext data'})


    def test_interface_implementation(self):
        """
        It implements the ISFTPServer interface.
        """
        self.assertTrue(
            filetransfer.ISFTPServer.providedBy(self.server.client),
            "ISFTPServer not provided by %r" % (self.server.client,))


    def test_openedFileClosedWithConnection(self):
        """
        A file opened with C{openFile} is close when the connection is lost.
        """
        d = self.client.openFile(b"testfile1", filetransfer.FXF_READ |
                                 filetransfer.FXF_WRITE, {})
        self._emptyBuffers()

        oldClose = os.close
        closed = []
        def close(fd):
            closed.append(fd)
            oldClose(fd)

        self.patch(os, "close", close)

        def _fileOpened(openFile):
            fd = self.server.openFiles[openFile.handle[4:]].fd
            self.serverTransport.loseConnection()
            self.clientTransport.loseConnection()
            self.serverTransport.clearBuffer()
            self.clientTransport.clearBuffer()
            self.assertEqual(self.server.openFiles, {})
            self.assertIn(fd, closed)

        d.addCallback(_fileOpened)
        return d


    def test_openedDirectoryClosedWithConnection(self):
        """
        A directory opened with C{openDirectory} is close when the connection
        is lost.
        """
        d = self.client.openDirectory(b'')
        self._emptyBuffers()

        def _getFiles(openDir):
            self.serverTransport.loseConnection()
            self.clientTransport.loseConnection()
            self.serverTransport.clearBuffer()
            self.clientTransport.clearBuffer()
            self.assertEqual(self.server.openDirs, {})

        d.addCallback(_getFiles)
        return d


    def testOpenFileIO(self):
        d = self.client.openFile(b"testfile1", filetransfer.FXF_READ |
                                 filetransfer.FXF_WRITE, {})
        self._emptyBuffers()

        def _fileOpened(openFile):
            self.assertEqual(openFile, filetransfer.ISFTPFile(openFile))
            d = _readChunk(openFile)
            d.addCallback(_writeChunk, openFile)
            return d

        def _readChunk(openFile):
            d = openFile.readChunk(0, 20)
            self._emptyBuffers()
            d.addCallback(self.assertEqual, b'a'*10 + b'b'*10)
            return d

        def _writeChunk(_, openFile):
            d = openFile.writeChunk(20, b'c'*10)
            self._emptyBuffers()
            d.addCallback(_readChunk2, openFile)
            return d

        def _readChunk2(_, openFile):
            d = openFile.readChunk(0, 30)
            self._emptyBuffers()
            d.addCallback(self.assertEqual, b'a'*10 + b'b'*10 + b'c'*10)
            return d

        d.addCallback(_fileOpened)
        return d

    def testClosedFileGetAttrs(self):
        d = self.client.openFile(b"testfile1", filetransfer.FXF_READ |
                                 filetransfer.FXF_WRITE, {})
        self._emptyBuffers()

        def _getAttrs(_, openFile):
            d = openFile.getAttrs()
            self._emptyBuffers()
            return d

        def _err(f):
            self.flushLoggedErrors()
            return f

        def _close(openFile):
            d = openFile.close()
            self._emptyBuffers()
            d.addCallback(_getAttrs, openFile)
            d.addErrback(_err)
            return self.assertFailure(d, filetransfer.SFTPError)

        d.addCallback(_close)
        return d

    def testOpenFileAttributes(self):
        d = self.client.openFile(b"testfile1", filetransfer.FXF_READ |
                                 filetransfer.FXF_WRITE, {})
        self._emptyBuffers()

        def _getAttrs(openFile):
            d = openFile.getAttrs()
            self._emptyBuffers()
            d.addCallback(_getAttrs2)
            return d

        def _getAttrs2(attrs1):
            d = self.client.getAttrs(b'testfile1')
            self._emptyBuffers()
            d.addCallback(self.assertEqual, attrs1)
            return d

        return d.addCallback(_getAttrs)


    def testOpenFileSetAttrs(self):
        # XXX test setAttrs
        # Ok, how about this for a start?  It caught a bug :)  -- spiv.
        d = self.client.openFile(b"testfile1", filetransfer.FXF_READ |
                                 filetransfer.FXF_WRITE, {})
        self._emptyBuffers()

        def _getAttrs(openFile):
            d = openFile.getAttrs()
            self._emptyBuffers()
            d.addCallback(_setAttrs)
            return d

        def _setAttrs(attrs):
            attrs['atime'] = 0
            d = self.client.setAttrs(b'testfile1', attrs)
            self._emptyBuffers()
            d.addCallback(_getAttrs2)
            d.addCallback(self.assertEqual, attrs)
            return d

        def _getAttrs2(_):
            d = self.client.getAttrs(b'testfile1')
            self._emptyBuffers()
            return d

        d.addCallback(_getAttrs)
        return d


    def test_openFileExtendedAttributes(self):
        """
        Check that L{filetransfer.FileTransferClient.openFile} can send
        extended attributes, that should be extracted server side. By default,
        they are ignored, so we just verify they are correctly parsed.
        """
        savedAttributes = {}
        oldOpenFile = self.server.client.openFile
        def openFile(filename, flags, attrs):
            savedAttributes.update(attrs)
            return oldOpenFile(filename, flags, attrs)
        self.server.client.openFile = openFile

        d = self.client.openFile(b"testfile1", filetransfer.FXF_READ |
                filetransfer.FXF_WRITE, {"ext_foo": b"bar"})
        self._emptyBuffers()

        def check(ign):
            self.assertEqual(savedAttributes, {"ext_foo": b"bar"})

        return d.addCallback(check)


    def testRemoveFile(self):
        d = self.client.getAttrs(b"testRemoveFile")
        self._emptyBuffers()
        def _removeFile(ignored):
            d = self.client.removeFile(b"testRemoveFile")
            self._emptyBuffers()
            return d
        d.addCallback(_removeFile)
        d.addCallback(_removeFile)
        return self.assertFailure(d, filetransfer.SFTPError)

    def testRenameFile(self):
        d = self.client.getAttrs(b"testRenameFile")
        self._emptyBuffers()
        def _rename(attrs):
            d = self.client.renameFile(b"testRenameFile", b"testRenamedFile")
            self._emptyBuffers()
            d.addCallback(_testRenamed, attrs)
            return d
        def _testRenamed(_, attrs):
            d = self.client.getAttrs(b"testRenamedFile")
            self._emptyBuffers()
            d.addCallback(self.assertEqual, attrs)
        return d.addCallback(_rename)

    def testDirectoryBad(self):
        d = self.client.getAttrs(b"testMakeDirectory")
        self._emptyBuffers()
        return self.assertFailure(d, filetransfer.SFTPError)

    def testDirectoryCreation(self):
        d = self.client.makeDirectory(b"testMakeDirectory", {})
        self._emptyBuffers()

        def _getAttrs(_):
            d = self.client.getAttrs(b"testMakeDirectory")
            self._emptyBuffers()
            return d

        # XXX not until version 4/5
        # self.assertEqual(filetransfer.FILEXFER_TYPE_DIRECTORY&attrs['type'],
        #                     filetransfer.FILEXFER_TYPE_DIRECTORY)

        def _removeDirectory(_):
            d = self.client.removeDirectory(b"testMakeDirectory")
            self._emptyBuffers()
            return d

        d.addCallback(_getAttrs)
        d.addCallback(_removeDirectory)
        d.addCallback(_getAttrs)
        return self.assertFailure(d, filetransfer.SFTPError)

    def testOpenDirectory(self):
        d = self.client.openDirectory(b'')
        self._emptyBuffers()
        files = []

        def _getFiles(openDir):
            def append(f):
                files.append(f)
                return openDir
            d = defer.maybeDeferred(openDir.next)
            self._emptyBuffers()
            d.addCallback(append)
            d.addCallback(_getFiles)
            d.addErrback(_close, openDir)
            return d

        def _checkFiles(ignored):
            fs = list(list(zip(*files))[0])
            fs.sort()
            self.assertEqual(fs,
                                 [b'.testHiddenFile', b'testDirectory',
                                  b'testRemoveFile', b'testRenameFile',
                                  b'testfile1'])

        def _close(_, openDir):
            d = openDir.close()
            self._emptyBuffers()
            return d

        d.addCallback(_getFiles)
        d.addCallback(_checkFiles)
        return d

    def testLinkDoesntExist(self):
        d = self.client.getAttrs(b'testLink')
        self._emptyBuffers()
        return self.assertFailure(d, filetransfer.SFTPError)

    def testLinkSharesAttrs(self):
        d = self.client.makeLink(b'testLink', b'testfile1')
        self._emptyBuffers()
        def _getFirstAttrs(_):
            d = self.client.getAttrs(b'testLink', 1)
            self._emptyBuffers()
            return d
        def _getSecondAttrs(firstAttrs):
            d = self.client.getAttrs(b'testfile1')
            self._emptyBuffers()
            d.addCallback(self.assertEqual, firstAttrs)
            return d
        d.addCallback(_getFirstAttrs)
        return d.addCallback(_getSecondAttrs)

    def testLinkPath(self):
        d = self.client.makeLink(b'testLink', b'testfile1')
        self._emptyBuffers()
        def _readLink(_):
            d = self.client.readLink(b'testLink')
            self._emptyBuffers()
            d.addCallback(
                self.assertEqual,
                os.path.join(
                    networkString(os.getcwd()), self.testDir, b'testfile1'))
            return d
        def _realPath(_):
            d = self.client.realPath(b'testLink')
            self._emptyBuffers()
            d.addCallback(
                self.assertEqual,
                os.path.join(
                    networkString(os.getcwd()), self.testDir, b'testfile1'))
            return d
        d.addCallback(_readLink)
        d.addCallback(_realPath)
        return d

    def testExtendedRequest(self):
        d = self.client.extendedRequest(b'testExtendedRequest', b'foo')
        self._emptyBuffers()
        d.addCallback(self.assertEqual, b'bar')
        d.addCallback(self._cbTestExtendedRequest)
        return d

    def _cbTestExtendedRequest(self, ignored):
        d = self.client.extendedRequest(b'testBadRequest', b'')
        self._emptyBuffers()
        return self.assertFailure(d, NotImplementedError)


class FakeConn:
    def sendClose(self, channel):
        pass


class FileTransferCloseTests(unittest.TestCase):

    if not unix:
        skip = "can't run on non-posix computers"

    def setUp(self):
        self.avatar = TestAvatar()

    def buildServerConnection(self):
        # make a server connection
        conn = connection.SSHConnection()
        # server connections have a 'self.transport.avatar'.
        class DummyTransport:
            def __init__(self):
                self.transport = self
            def sendPacket(self, kind, data):
                pass
            def logPrefix(self):
                return 'dummy transport'
        conn.transport = DummyTransport()
        conn.transport.avatar = self.avatar
        return conn

    def interceptConnectionLost(self, sftpServer):
        self.connectionLostFired = False
        origConnectionLost = sftpServer.connectionLost
        def connectionLost(reason):
            self.connectionLostFired = True
            origConnectionLost(reason)
        sftpServer.connectionLost = connectionLost

    def assertSFTPConnectionLost(self):
        self.assertTrue(self.connectionLostFired,
            "sftpServer's connectionLost was not called")

    def test_sessionClose(self):
        """
        Closing a session should notify an SFTP subsystem launched by that
        session.
        """
        # make a session
        testSession = session.SSHSession(conn=FakeConn(), avatar=self.avatar)

        # start an SFTP subsystem on the session
        testSession.request_subsystem(common.NS(b'sftp'))
        sftpServer = testSession.client.transport.proto

        # intercept connectionLost so we can check that it's called
        self.interceptConnectionLost(sftpServer)

        # close session
        testSession.closeReceived()

        self.assertSFTPConnectionLost()

    def test_clientClosesChannelOnConnnection(self):
        """
        A client sending CHANNEL_CLOSE should trigger closeReceived on the
        associated channel instance.
        """
        conn = self.buildServerConnection()

        # somehow get a session
        packet = common.NS(b'session') + struct.pack('>L', 0) * 3
        conn.ssh_CHANNEL_OPEN(packet)
        sessionChannel = conn.channels[0]

        sessionChannel.request_subsystem(common.NS(b'sftp'))
        sftpServer = sessionChannel.client.transport.proto
        self.interceptConnectionLost(sftpServer)

        # intercept closeReceived
        self.interceptConnectionLost(sftpServer)

        # close the connection
        conn.ssh_CHANNEL_CLOSE(struct.pack('>L', 0))

        self.assertSFTPConnectionLost()


    def test_stopConnectionServiceClosesChannel(self):
        """
        Closing an SSH connection should close all sessions within it.
        """
        conn = self.buildServerConnection()

        # somehow get a session
        packet = common.NS(b'session') + struct.pack('>L', 0) * 3
        conn.ssh_CHANNEL_OPEN(packet)
        sessionChannel = conn.channels[0]

        sessionChannel.request_subsystem(common.NS(b'sftp'))
        sftpServer = sessionChannel.client.transport.proto
        self.interceptConnectionLost(sftpServer)

        # close the connection
        conn.serviceStopped()

        self.assertSFTPConnectionLost()



class ConstantsTests(unittest.TestCase):
    """
    Tests for the constants used by the SFTP protocol implementation.

    @ivar filexferSpecExcerpts: Excerpts from the
        draft-ietf-secsh-filexfer-02.txt (draft) specification of the SFTP
        protocol.  There are more recent drafts of the specification, but this
        one describes version 3, which is what conch (and OpenSSH) implements.
    """


    filexferSpecExcerpts = [
        """
           The following values are defined for packet types.

                #define SSH_FXP_INIT                1
                #define SSH_FXP_VERSION             2
                #define SSH_FXP_OPEN                3
                #define SSH_FXP_CLOSE               4
                #define SSH_FXP_READ                5
                #define SSH_FXP_WRITE               6
                #define SSH_FXP_LSTAT               7
                #define SSH_FXP_FSTAT               8
                #define SSH_FXP_SETSTAT             9
                #define SSH_FXP_FSETSTAT           10
                #define SSH_FXP_OPENDIR            11
                #define SSH_FXP_READDIR            12
                #define SSH_FXP_REMOVE             13
                #define SSH_FXP_MKDIR              14
                #define SSH_FXP_RMDIR              15
                #define SSH_FXP_REALPATH           16
                #define SSH_FXP_STAT               17
                #define SSH_FXP_RENAME             18
                #define SSH_FXP_READLINK           19
                #define SSH_FXP_SYMLINK            20
                #define SSH_FXP_STATUS            101
                #define SSH_FXP_HANDLE            102
                #define SSH_FXP_DATA              103
                #define SSH_FXP_NAME              104
                #define SSH_FXP_ATTRS             105
                #define SSH_FXP_EXTENDED          200
                #define SSH_FXP_EXTENDED_REPLY    201

           Additional packet types should only be defined if the protocol
           version number (see Section ``Protocol Initialization'') is
           incremented, and their use MUST be negotiated using the version
           number.  However, the SSH_FXP_EXTENDED and SSH_FXP_EXTENDED_REPLY
           packets can be used to implement vendor-specific extensions.  See
           Section ``Vendor-Specific-Extensions'' for more details.
        """,
        """
            The flags bits are defined to have the following values:

                #define SSH_FILEXFER_ATTR_SIZE          0x00000001
                #define SSH_FILEXFER_ATTR_UIDGID        0x00000002
                #define SSH_FILEXFER_ATTR_PERMISSIONS   0x00000004
                #define SSH_FILEXFER_ATTR_ACMODTIME     0x00000008
                #define SSH_FILEXFER_ATTR_EXTENDED      0x80000000

        """,
        """
            The `pflags' field is a bitmask.  The following bits have been
           defined.

                #define SSH_FXF_READ            0x00000001
                #define SSH_FXF_WRITE           0x00000002
                #define SSH_FXF_APPEND          0x00000004
                #define SSH_FXF_CREAT           0x00000008
                #define SSH_FXF_TRUNC           0x00000010
                #define SSH_FXF_EXCL            0x00000020
        """,
        """
            Currently, the following values are defined (other values may be
           defined by future versions of this protocol):

                #define SSH_FX_OK                            0
                #define SSH_FX_EOF                           1
                #define SSH_FX_NO_SUCH_FILE                  2
                #define SSH_FX_PERMISSION_DENIED             3
                #define SSH_FX_FAILURE                       4
                #define SSH_FX_BAD_MESSAGE                   5
                #define SSH_FX_NO_CONNECTION                 6
                #define SSH_FX_CONNECTION_LOST               7
                #define SSH_FX_OP_UNSUPPORTED                8
        """]


    def test_constantsAgainstSpec(self):
        """
        The constants used by the SFTP protocol implementation match those
        found by searching through the spec.
        """
        constants = {}
        for excerpt in self.filexferSpecExcerpts:
            for line in excerpt.splitlines():
                m = re.match('^\s*#define SSH_([A-Z_]+)\s+([0-9x]*)\s*$', line)
                if m:
                    constants[m.group(1)] = long(m.group(2), 0)
        self.assertTrue(
            len(constants) > 0, "No constants found (the test must be buggy).")
        for k, v in constants.items():
            self.assertEqual(v, getattr(filetransfer, k))



class RawPacketDataTests(unittest.TestCase):
    """
    Tests for L{filetransfer.FileTransferClient} which explicitly craft certain
    less common protocol messages to exercise their handling.
    """
    def setUp(self):
        self.ftc = filetransfer.FileTransferClient()


    def test_packetSTATUS(self):
        """
        A STATUS packet containing a result code, a message, and a language is
        parsed to produce the result of an outstanding request L{Deferred}.

        @see: U{section 9.1<http://tools.ietf.org/html/draft-ietf-secsh-filexfer-13#section-9.1>}
            of the SFTP Internet-Draft.
        """
        d = defer.Deferred()
        d.addCallback(self._cbTestPacketSTATUS)
        self.ftc.openRequests[1] = d
        data = struct.pack('!LL', 1, filetransfer.FX_OK) + common.NS(b'msg') + common.NS(b'lang')
        self.ftc.packet_STATUS(data)
        return d


    def _cbTestPacketSTATUS(self, result):
        """
        Assert that the result is a two-tuple containing the message and
        language from the STATUS packet.
        """
        self.assertEqual(result[0], b'msg')
        self.assertEqual(result[1], b'lang')


    def test_packetSTATUSShort(self):
        """
        A STATUS packet containing only a result code can also be parsed to
        produce the result of an outstanding request L{Deferred}.  Such packets
        are sent by some SFTP implementations, though not strictly legal.

        @see: U{section 9.1<http://tools.ietf.org/html/draft-ietf-secsh-filexfer-13#section-9.1>}
            of the SFTP Internet-Draft.
        """
        d = defer.Deferred()
        d.addCallback(self._cbTestPacketSTATUSShort)
        self.ftc.openRequests[1] = d
        data = struct.pack('!LL', 1, filetransfer.FX_OK)
        self.ftc.packet_STATUS(data)
        return d


    def _cbTestPacketSTATUSShort(self, result):
        """
        Assert that the result is a two-tuple containing empty strings, since
        the STATUS packet had neither a message nor a language.
        """
        self.assertEqual(result[0], b'')
        self.assertEqual(result[1], b'')


    def test_packetSTATUSWithoutLang(self):
        """
        A STATUS packet containing a result code and a message but no language
        can also be parsed to produce the result of an outstanding request
        L{Deferred}.  Such packets are sent by some SFTP implementations, though
        not strictly legal.

        @see: U{section 9.1<http://tools.ietf.org/html/draft-ietf-secsh-filexfer-13#section-9.1>}
            of the SFTP Internet-Draft.
        """
        d = defer.Deferred()
        d.addCallback(self._cbTestPacketSTATUSWithoutLang)
        self.ftc.openRequests[1] = d
        data = struct.pack('!LL', 1, filetransfer.FX_OK) + common.NS(b'msg')
        self.ftc.packet_STATUS(data)
        return d


    def _cbTestPacketSTATUSWithoutLang(self, result):
        """
        Assert that the result is a two-tuple containing the message from the
        STATUS packet and an empty string, since the language was missing.
        """
        self.assertEqual(result[0], b'msg')
        self.assertEqual(result[1], b'')
