# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Assorted functionality which is commonly useful when writing unit tests.

This module has been deprecated, please use twisted.internet.testing
instead.
"""
from twisted.internet import testing

__all__ = [
    "AccumulatingProtocol",
    "LineSendingProtocol",
    "FakeDatagramTransport",
    "StringTransport",
    "StringTransportWithDisconnection",
    "StringIOWithoutClosing",
    "_FakeConnector",
    "_FakePort",
    "MemoryReactor",
    "MemoryReactorClock",
    "RaisingMemoryReactor",
    "NonStreamingProducer",
    "waitUntilAllDisconnected",
    "EventLoggingObserver",
]


AccumulatingProtocol = testing.AccumulatingProtocol
LineSendingProtocol = testing.LineSendingProtocol
FakeDatagramTransport = testing.FakeDatagramTransport
StringTransport = testing.StringTransport
StringTransportWithDisconnection = testing.StringTransportWithDisconnection
StringIOWithoutClosing = testing.StringIOWithoutClosing
_FakeConnector = testing._FakeConnector
_FakePort = testing._FakePort
MemoryReactor = testing.MemoryReactor
MemoryReactorClock = testing.MemoryReactorClock
RaisingMemoryReactor = testing.RaisingMemoryReactor
NonStreamingProducer = testing.NonStreamingProducer
waitUntilAllDisconnected = testing.waitUntilAllDisconnected
EventLoggingObserver = testing.EventLoggingObserver
