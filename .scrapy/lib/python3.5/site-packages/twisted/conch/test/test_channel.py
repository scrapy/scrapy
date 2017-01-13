# Copyright Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test ssh/channel.py.
"""

from __future__ import division, absolute_import

from zope.interface.verify import verifyObject

try:
    from twisted.conch.ssh import channel
    from twisted.conch.ssh.address import SSHTransportAddress
    from twisted.conch.ssh.transport import SSHServerTransport
    from twisted.conch.ssh.service import SSHService
    from twisted.internet import interfaces
    from twisted.internet.address import IPv4Address
    from twisted.test.proto_helpers import StringTransport
    skipTest = None
except ImportError:
    skipTest = 'Conch SSH not supported.'
    SSHService = object
from twisted.trial import unittest
from twisted.python.compat import intToBytes


class MockConnection(SSHService):
    """
    A mock for twisted.conch.ssh.connection.SSHConnection.  Record the data
    that channels send, and when they try to close the connection.

    @ivar data: a L{dict} mapping channel id #s to lists of data sent by that
        channel.
    @ivar extData: a L{dict} mapping channel id #s to lists of 2-tuples
        (extended data type, data) sent by that channel.
    @ivar closes: a L{dict} mapping channel id #s to True if that channel sent
        a close message.
    """

    def __init__(self):
        self.data = {}
        self.extData = {}
        self.closes = {}


    def logPrefix(self):
        """
        Return our logging prefix.
        """
        return "MockConnection"


    def sendData(self, channel, data):
        """
        Record the sent data.
        """
        self.data.setdefault(channel, []).append(data)


    def sendExtendedData(self, channel, type, data):
        """
        Record the sent extended data.
        """
        self.extData.setdefault(channel, []).append((type, data))


    def sendClose(self, channel):
        """
        Record that the channel sent a close message.
        """
        self.closes[channel] = True



def connectSSHTransport(service, hostAddress=None, peerAddress=None):
    """
    Connect a SSHTransport which is already connected to a remote peer to
    the channel under test.

    @param service: Service used over the connected transport.
    @type service: L{SSHService}

    @param hostAddress: Local address of the connected transport.
    @type hostAddress: L{interfaces.IAddress}

    @param peerAddress: Remote address of the connected transport.
    @type peerAddress: L{interfaces.IAddress}
    """
    transport = SSHServerTransport()
    transport.makeConnection(StringTransport(
        hostAddress=hostAddress, peerAddress=peerAddress))
    transport.setService(service)



class ChannelTests(unittest.TestCase):
    """
    Tests for L{SSHChannel}.
    """

    skip = skipTest

    def setUp(self):
        """
        Initialize the channel.  remoteMaxPacket is 10 so that data is able
        to be sent (the default of 0 means no data is sent because no packets
        are made).
        """
        self.conn = MockConnection()
        self.channel = channel.SSHChannel(conn=self.conn,
                remoteMaxPacket=10)
        self.channel.name = b'channel'


    def test_interface(self):
        """
        L{SSHChannel} instances provide L{interfaces.ITransport}.
        """
        self.assertTrue(verifyObject(interfaces.ITransport, self.channel))


    def test_init(self):
        """
        Test that SSHChannel initializes correctly.  localWindowSize defaults
        to 131072 (2**17) and localMaxPacket to 32768 (2**15) as reasonable
        defaults (what OpenSSH uses for those variables).

        The values in the second set of assertions are meaningless; they serve
        only to verify that the instance variables are assigned in the correct
        order.
        """
        c = channel.SSHChannel(conn=self.conn)
        self.assertEqual(c.localWindowSize, 131072)
        self.assertEqual(c.localWindowLeft, 131072)
        self.assertEqual(c.localMaxPacket, 32768)
        self.assertEqual(c.remoteWindowLeft, 0)
        self.assertEqual(c.remoteMaxPacket, 0)
        self.assertEqual(c.conn, self.conn)
        self.assertIsNone(c.data)
        self.assertIsNone(c.avatar)

        c2 = channel.SSHChannel(1, 2, 3, 4, 5, 6, 7)
        self.assertEqual(c2.localWindowSize, 1)
        self.assertEqual(c2.localWindowLeft, 1)
        self.assertEqual(c2.localMaxPacket, 2)
        self.assertEqual(c2.remoteWindowLeft, 3)
        self.assertEqual(c2.remoteMaxPacket, 4)
        self.assertEqual(c2.conn, 5)
        self.assertEqual(c2.data, 6)
        self.assertEqual(c2.avatar, 7)


    def test_str(self):
        """
        Test that str(SSHChannel) works gives the channel name and local and
        remote windows at a glance..
        """
        self.assertEqual(
                str(self.channel), '<SSHChannel channel (lw 131072 rw 0)>')
        self.assertEqual(
                str(channel.SSHChannel(localWindow=1)),
                '<SSHChannel None (lw 1 rw 0)>')


    def test_bytes(self):
        """
        Test that bytes(SSHChannel) works, gives the channel name and
        local and remote windows at a glance..

        """
        self.assertEqual(
            self.channel.__bytes__(),
            b'<SSHChannel channel (lw 131072 rw 0)>')
        self.assertEqual(
            channel.SSHChannel(localWindow=1).__bytes__(),
            b'<SSHChannel None (lw 1 rw 0)>')


    def test_logPrefix(self):
        """
        Test that SSHChannel.logPrefix gives the name of the channel, the
        local channel ID and the underlying connection.
        """
        self.assertEqual(self.channel.logPrefix(), 'SSHChannel channel '
                '(unknown) on MockConnection')


    def test_addWindowBytes(self):
        """
        Test that addWindowBytes adds bytes to the window and resumes writing
        if it was paused.
        """
        cb = [False]
        def stubStartWriting():
            cb[0] = True
        self.channel.startWriting = stubStartWriting
        self.channel.write(b'test')
        self.channel.writeExtended(1, b'test')
        self.channel.addWindowBytes(50)
        self.assertEqual(self.channel.remoteWindowLeft, 50 - 4 - 4)
        self.assertTrue(self.channel.areWriting)
        self.assertTrue(cb[0])
        self.assertEqual(self.channel.buf, b'')
        self.assertEqual(self.conn.data[self.channel], [b'test'])
        self.assertEqual(self.channel.extBuf, [])
        self.assertEqual(self.conn.extData[self.channel], [(1, b'test')])

        cb[0] = False
        self.channel.addWindowBytes(20)
        self.assertFalse(cb[0])

        self.channel.write(b'a'*80)
        self.channel.loseConnection()
        self.channel.addWindowBytes(20)
        self.assertFalse(cb[0])


    def test_requestReceived(self):
        """
        Test that requestReceived handles requests by dispatching them to
        request_* methods.
        """
        self.channel.request_test_method = lambda data: data == b''
        self.assertTrue(self.channel.requestReceived(b'test-method', b''))
        self.assertFalse(self.channel.requestReceived(b'test-method', b'a'))
        self.assertFalse(self.channel.requestReceived(b'bad-method', b''))


    def test_closeReceieved(self):
        """
        Test that the default closeReceieved closes the connection.
        """
        self.assertFalse(self.channel.closing)
        self.channel.closeReceived()
        self.assertTrue(self.channel.closing)


    def test_write(self):
        """
        Test that write handles data correctly.  Send data up to the size
        of the remote window, splitting the data into packets of length
        remoteMaxPacket.
        """
        cb = [False]
        def stubStopWriting():
            cb[0] = True
        # no window to start with
        self.channel.stopWriting = stubStopWriting
        self.channel.write(b'd')
        self.channel.write(b'a')
        self.assertFalse(self.channel.areWriting)
        self.assertTrue(cb[0])
        # regular write
        self.channel.addWindowBytes(20)
        self.channel.write(b'ta')
        data = self.conn.data[self.channel]
        self.assertEqual(data, [b'da', b'ta'])
        self.assertEqual(self.channel.remoteWindowLeft, 16)
        # larger than max packet
        self.channel.write(b'12345678901')
        self.assertEqual(data, [b'da', b'ta', b'1234567890', b'1'])
        self.assertEqual(self.channel.remoteWindowLeft, 5)
        # running out of window
        cb[0] = False
        self.channel.write(b'123456')
        self.assertFalse(self.channel.areWriting)
        self.assertTrue(cb[0])
        self.assertEqual(data, [b'da', b'ta', b'1234567890', b'1', b'12345'])
        self.assertEqual(self.channel.buf, b'6')
        self.assertEqual(self.channel.remoteWindowLeft, 0)


    def test_writeExtended(self):
        """
        Test that writeExtended handles data correctly.  Send extended data
        up to the size of the window, splitting the extended data into packets
        of length remoteMaxPacket.
        """
        cb = [False]
        def stubStopWriting():
            cb[0] = True
        # no window to start with
        self.channel.stopWriting = stubStopWriting
        self.channel.writeExtended(1, b'd')
        self.channel.writeExtended(1, b'a')
        self.channel.writeExtended(2, b't')
        self.assertFalse(self.channel.areWriting)
        self.assertTrue(cb[0])
        # regular write
        self.channel.addWindowBytes(20)
        self.channel.writeExtended(2, b'a')
        data = self.conn.extData[self.channel]
        self.assertEqual(data, [(1, b'da'), (2, b't'), (2, b'a')])
        self.assertEqual(self.channel.remoteWindowLeft, 16)
        # larger than max packet
        self.channel.writeExtended(3, b'12345678901')
        self.assertEqual(data, [(1, b'da'), (2, b't'), (2, b'a'),
            (3, b'1234567890'), (3, b'1')])
        self.assertEqual(self.channel.remoteWindowLeft, 5)
        # running out of window
        cb[0] = False
        self.channel.writeExtended(4, b'123456')
        self.assertFalse(self.channel.areWriting)
        self.assertTrue(cb[0])
        self.assertEqual(data, [(1, b'da'), (2, b't'), (2, b'a'),
            (3, b'1234567890'), (3, b'1'), (4, b'12345')])
        self.assertEqual(self.channel.extBuf, [[4, b'6']])
        self.assertEqual(self.channel.remoteWindowLeft, 0)


    def test_writeSequence(self):
        """
        Test that writeSequence is equivalent to write(''.join(sequece)).
        """
        self.channel.addWindowBytes(20)
        self.channel.writeSequence(map(intToBytes, range(10)))
        self.assertEqual(self.conn.data[self.channel], [b'0123456789'])


    def test_loseConnection(self):
        """
        Tesyt that loseConnection() doesn't close the channel until all
        the data is sent.
        """
        self.channel.write(b'data')
        self.channel.writeExtended(1, b'datadata')
        self.channel.loseConnection()
        self.assertIsNone(self.conn.closes.get(self.channel))
        self.channel.addWindowBytes(4) # send regular data
        self.assertIsNone(self.conn.closes.get(self.channel))
        self.channel.addWindowBytes(8) # send extended data
        self.assertTrue(self.conn.closes.get(self.channel))


    def test_getPeer(self):
        """
        L{SSHChannel.getPeer} returns the same object as the underlying
        transport's C{getPeer} method returns.
        """
        peer = IPv4Address('TCP', '192.168.0.1', 54321)
        connectSSHTransport(service=self.channel.conn, peerAddress=peer)

        self.assertEqual(SSHTransportAddress(peer), self.channel.getPeer())


    def test_getHost(self):
        """
        L{SSHChannel.getHost} returns the same object as the underlying
        transport's C{getHost} method returns.
        """
        host = IPv4Address('TCP', '127.0.0.1', 12345)
        connectSSHTransport(service=self.channel.conn, hostAddress=host)

        self.assertEqual(SSHTransportAddress(host), self.channel.getHost())
