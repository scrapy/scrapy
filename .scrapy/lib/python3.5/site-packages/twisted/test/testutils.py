# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
I{Private} test utilities for use throughout Twisted's test suite.  Unlike
C{proto_helpers}, this is no exception to the
don't-use-it-outside-Twisted-we-won't-maintain-compatibility rule!

@note: Maintainers be aware: things in this module should be gradually promoted
    to more full-featured test helpers and exposed as public API as your
    maintenance time permits.  In order to be public API though, they need
    their own test cases.
"""

from io import BytesIO

from xml.dom import minidom as dom

from twisted.internet.protocol import FileWrapper

class IOPump:
    """Utility to pump data between clients and servers for protocol testing.

    Perhaps this is a utility worthy of being in protocol.py?
    """
    def __init__(self, client, server, clientIO, serverIO):
        self.client = client
        self.server = server
        self.clientIO = clientIO
        self.serverIO = serverIO

    def flush(self):
        "Pump until there is no more input or output."
        while self.pump():
            pass

    def pump(self):
        """Move data back and forth.

        Returns whether any data was moved.
        """
        self.clientIO.seek(0)
        self.serverIO.seek(0)
        cData = self.clientIO.read()
        sData = self.serverIO.read()
        self.clientIO.seek(0)
        self.serverIO.seek(0)
        self.clientIO.truncate()
        self.serverIO.truncate()
        for byte in cData:
            self.server.dataReceived(byte)
        for byte in sData:
            self.client.dataReceived(byte)
        if cData or sData:
            return 1
        else:
            return 0


def returnConnected(server, client):
    """Take two Protocol instances and connect them.
    """
    cio = BytesIO()
    sio = BytesIO()
    client.makeConnection(FileWrapper(cio))
    server.makeConnection(FileWrapper(sio))
    pump = IOPump(client, server, cio, sio)
    # Challenge-response authentication:
    pump.flush()
    # Uh...
    pump.flush()
    return pump



class XMLAssertionMixin(object):
    """
    Test mixin defining a method for comparing serialized XML documents.

    Must be mixed in to a L{test case<unittest.TestCase>}.
    """

    def assertXMLEqual(self, first, second):
        """
        Verify that two strings represent the same XML document.

        @param first: An XML string.
        @type first: L{bytes}

        @param second: An XML string that should match C{first}.
        @type second: L{bytes}
        """
        self.assertEqual(
            dom.parseString(first).toxml(),
            dom.parseString(second).toxml())



class _Equal(object):
    """
    A class the instances of which are equal to anything and everything.
    """
    def __eq__(self, other):
        return True


    def __ne__(self, other):
        return False



class _NotEqual(object):
    """
    A class the instances of which are equal to nothing.
    """
    def __eq__(self, other):
        return False


    def __ne__(self, other):
        return True



class ComparisonTestsMixin(object):
    """
    A mixin which defines a method for making assertions about the correctness
    of an implementation of C{==} and C{!=}.

    Use this to unit test objects which follow the common convention for C{==}
    and C{!=}:

        - The object compares equal to itself
        - The object cooperates with unrecognized types to allow them to
          implement the comparison
        - The object implements not-equal as the opposite of equal
    """
    def assertNormalEqualityImplementation(self, firstValueOne, secondValueOne,
                                           valueTwo):
        """
        Assert that C{firstValueOne} is equal to C{secondValueOne} but not
        equal to C{valueOne} and that it defines equality cooperatively with
        other types it doesn't know about.

        @param firstValueOne: An object which is expected to compare as equal to
            C{secondValueOne} and not equal to C{valueTwo}.

        @param secondValueOne: A different object than C{firstValueOne} but
            which is expected to compare equal to that object.

        @param valueTwo: An object which is expected to compare as not equal to
            C{firstValueOne}.
        """
        # This doesn't use assertEqual and assertNotEqual because the exact
        # operator those functions use is not very well defined.  The point
        # of these assertions is to check the results of the use of specific
        # operators (precisely to ensure that using different permutations
        # (eg "x == y" or "not (x != y)") which should yield the same results
        # actually does yield the same result). -exarkun
        self.assertTrue(firstValueOne == firstValueOne)
        self.assertTrue(firstValueOne == secondValueOne)
        self.assertFalse(firstValueOne == valueTwo)
        self.assertFalse(firstValueOne != firstValueOne)
        self.assertFalse(firstValueOne != secondValueOne)
        self.assertTrue(firstValueOne != valueTwo)
        self.assertTrue(firstValueOne == _Equal())
        self.assertFalse(firstValueOne != _Equal())
        self.assertFalse(firstValueOne == _NotEqual())
        self.assertTrue(firstValueOne != _NotEqual())
