# -*- test-case-name: twisted.web.test.test_newclient -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
An U{HTTP 1.1<http://www.w3.org/Protocols/rfc2616/rfc2616.html>} client.

The way to use the functionality provided by this module is to:

  - Connect a L{HTTP11ClientProtocol} to an HTTP server
  - Create a L{Request} with the appropriate data
  - Pass the request to L{HTTP11ClientProtocol.request}
  - The returned Deferred will fire with a L{Response} object
  - Create a L{IProtocol} provider which can handle the response body
  - Connect it to the response with L{Response.deliverBody}
  - When the protocol's C{connectionLost} method is called, the response is
    complete.  See L{Response.deliverBody} for details.

Various other classes in this module support this usage:

  - HTTPParser is the basic HTTP parser.  It can handle the parts of HTTP which
    are symmetric between requests and responses.

  - HTTPClientParser extends HTTPParser to handle response-specific parts of
    HTTP.  One instance is created for each request to parse the corresponding
    response.
"""

__metaclass__ = type

from zope.interface import implements

from twisted.python import log
from twisted.python.reflect import fullyQualifiedName
from twisted.python.failure import Failure
from twisted.internet.interfaces import IConsumer, IPushProducer
from twisted.internet.error import ConnectionDone
from twisted.internet.defer import Deferred, succeed, fail, maybeDeferred
from twisted.internet.defer import CancelledError
from twisted.internet.protocol import Protocol
from twisted.web.iweb import UNKNOWN_LENGTH, IResponse
from twisted.web.http import NO_CONTENT, NOT_MODIFIED
from twisted.web.http import _DataLoss, PotentialDataLoss
from twisted.web.http import _IdentityTransferDecoder, _ChunkedTransferDecoder

from twisted.web._newclient import (
    BadHeaders, ExcessWrite, ParseError, BadResponseVersion, _WrapperException,
    RequestGenerationFailed, RequestTransmissionFailed, ConnectionAborted,
    WrongBodyLength, ResponseDone, ResponseFailed, RequestNotSent,
    ResponseNeverReceived, HTTPParser, HTTPClientParser, Request,
    LengthEnforcingConsumer, makeStatefulDispatcher, Response, ChunkedEncoder,
    TransportProxyProducer, HTTP11ClientProtocol
)

# States HTTPParser can be in
STATUS = 'STATUS'
HEADER = 'HEADER'
BODY = 'BODY'
DONE = 'DONE'
