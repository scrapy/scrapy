# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.protocols.haproxy._parser}.
"""
from typing import Type, Union

from twisted.internet.endpoints import (
    TCP4ServerEndpoint,
    TCP6ServerEndpoint,
    UNIXServerEndpoint,
    _parse as parseEndpoint,
    _WrapperServerEndpoint,
    serverFromString,
)
from twisted.test.proto_helpers import MemoryReactor
from twisted.trial.unittest import SynchronousTestCase as TestCase
from .._parser import unparseEndpoint
from .._wrapper import HAProxyWrappingFactory


class UnparseEndpointTests(TestCase):
    """
    Tests to ensure that un-parsing an endpoint string round trips through
    escaping properly.
    """

    def check(self, input: str) -> None:
        """
        Check that the input unparses into the output, raising an assertion
        error if it doesn't.

        @param input: an input in endpoint-string-description format.  (To
            ensure determinism, keyword arguments should be in alphabetical
            order.)
        @type input: native L{str}
        """
        self.assertEqual(unparseEndpoint(*parseEndpoint(input)), input)

    def test_basicUnparse(self) -> None:
        """
        An individual word.
        """
        self.check("word")

    def test_multipleArguments(self) -> None:
        """
        Multiple arguments.
        """
        self.check("one:two")

    def test_keywords(self) -> None:
        """
        Keyword arguments.
        """
        self.check("aleph=one:bet=two")

    def test_colonInArgument(self) -> None:
        """
        Escaped ":".
        """
        self.check("hello\\:colon\\:world")

    def test_colonInKeywordValue(self) -> None:
        """
        Escaped ":" in keyword value.
        """
        self.check("hello=\\:")

    def test_colonInKeywordName(self) -> None:
        """
        Escaped ":" in keyword name.
        """
        self.check("\\:=hello")


class HAProxyServerParserTests(TestCase):
    """
    Tests that the parser generates the correct endpoints.
    """

    def onePrefix(
        self,
        description: str,
        expectedClass: Union[
            Type[TCP4ServerEndpoint],
            Type[TCP6ServerEndpoint],
            Type[UNIXServerEndpoint],
        ],
    ) -> _WrapperServerEndpoint:
        """
        Test the C{haproxy} enpdoint prefix against one sub-endpoint type.

        @param description: A string endpoint description beginning with
            C{haproxy}.
        @type description: native L{str}

        @param expectedClass: the expected sub-endpoint class given the
            description.
        @type expectedClass: L{type}

        @return: the parsed endpoint
        @rtype: L{IStreamServerEndpoint}

        @raise twisted.trial.unittest.Failtest: if the parsed endpoint doesn't
            match expectations.
        """
        reactor = MemoryReactor()
        endpoint = serverFromString(reactor, description)
        self.assertIsInstance(endpoint, _WrapperServerEndpoint)
        assert isinstance(endpoint, _WrapperServerEndpoint)
        self.assertIsInstance(endpoint._wrappedEndpoint, expectedClass)
        self.assertIs(endpoint._wrapperFactory, HAProxyWrappingFactory)
        return endpoint

    def test_tcp4(self) -> None:
        """
        Test if the parser generates a wrapped TCP4 endpoint.
        """
        self.onePrefix("haproxy:tcp:8080", TCP4ServerEndpoint)

    def test_tcp6(self) -> None:
        """
        Test if the parser generates a wrapped TCP6 endpoint.
        """
        self.onePrefix("haproxy:tcp6:8080", TCP6ServerEndpoint)

    def test_unix(self) -> None:
        """
        Test if the parser generates a wrapped UNIX endpoint.
        """
        self.onePrefix("haproxy:unix:address=/tmp/socket", UNIXServerEndpoint)
