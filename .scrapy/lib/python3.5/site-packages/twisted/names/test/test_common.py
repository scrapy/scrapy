# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.names.common}.
"""

from __future__ import division, absolute_import

from zope.interface.verify import verifyClass

from twisted.internet.interfaces import IResolver
from twisted.trial.unittest import SynchronousTestCase
from twisted.python.failure import Failure
from twisted.names.common import ResolverBase
from twisted.names.dns import EFORMAT, ESERVER, ENAME, ENOTIMP, EREFUSED, Query
from twisted.names.error import DNSFormatError, DNSServerError, DNSNameError
from twisted.names.error import DNSNotImplementedError, DNSQueryRefusedError
from twisted.names.error import DNSUnknownError


class ExceptionForCodeTests(SynchronousTestCase):
    """
    Tests for L{ResolverBase.exceptionForCode}.
    """
    def setUp(self):
        self.exceptionForCode = ResolverBase().exceptionForCode


    def test_eformat(self):
        """
        L{ResolverBase.exceptionForCode} converts L{EFORMAT} to
        L{DNSFormatError}.
        """
        self.assertIs(self.exceptionForCode(EFORMAT), DNSFormatError)


    def test_eserver(self):
        """
        L{ResolverBase.exceptionForCode} converts L{ESERVER} to
        L{DNSServerError}.
        """
        self.assertIs(self.exceptionForCode(ESERVER), DNSServerError)


    def test_ename(self):
        """
        L{ResolverBase.exceptionForCode} converts L{ENAME} to L{DNSNameError}.
        """
        self.assertIs(self.exceptionForCode(ENAME), DNSNameError)


    def test_enotimp(self):
        """
        L{ResolverBase.exceptionForCode} converts L{ENOTIMP} to
        L{DNSNotImplementedError}.
        """
        self.assertIs(self.exceptionForCode(ENOTIMP), DNSNotImplementedError)


    def test_erefused(self):
        """
        L{ResolverBase.exceptionForCode} converts L{EREFUSED} to
        L{DNSQueryRefusedError}.
        """
        self.assertIs(self.exceptionForCode(EREFUSED), DNSQueryRefusedError)


    def test_other(self):
        """
        L{ResolverBase.exceptionForCode} converts any other response code to
        L{DNSUnknownError}.
        """
        self.assertIs(self.exceptionForCode(object()), DNSUnknownError)



class QueryTests(SynchronousTestCase):
    """
    Tests for L{ResolverBase.query}.
    """

    def test_resolverBaseProvidesIResolver(self):
        """
        L{ResolverBase} provides the L{IResolver} interface.
        """
        verifyClass(IResolver, ResolverBase)


    def test_typeToMethodDispatch(self):
        """
        L{ResolverBase.query} looks up a method to invoke using the type of the
        query passed to it and the C{typeToMethod} mapping on itself.
        """
        results = []
        resolver = ResolverBase()
        resolver.typeToMethod = {
            12345: lambda query, timeout: results.append((query, timeout))}
        query = Query(name=b"example.com", type=12345)
        resolver.query(query, 123)
        self.assertEqual([(b"example.com", 123)], results)


    def test_typeToMethodResult(self):
        """
        L{ResolverBase.query} returns a L{Deferred} which fires with the result
        of the method found in the C{typeToMethod} mapping for the type of the
        query passed to it.
        """
        expected = object()
        resolver = ResolverBase()
        resolver.typeToMethod = {54321: lambda query, timeout: expected}
        query = Query(name=b"example.com", type=54321)
        queryDeferred = resolver.query(query, 123)
        result = []
        queryDeferred.addBoth(result.append)
        self.assertEqual(expected, result[0])


    def test_unknownQueryType(self):
        """
        L{ResolverBase.query} returns a L{Deferred} which fails with
        L{NotImplementedError} when called with a query of a type not present in
        its C{typeToMethod} dictionary.
        """
        resolver = ResolverBase()
        resolver.typeToMethod = {}
        query = Query(name=b"example.com", type=12345)
        queryDeferred = resolver.query(query, 123)
        result = []
        queryDeferred.addBoth(result.append)
        self.assertIsInstance(result[0], Failure)
        result[0].trap(NotImplementedError)
