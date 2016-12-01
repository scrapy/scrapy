# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Interface documentation.

Maintainer: Itamar Shtull-Trauring
"""

from __future__ import division, absolute_import

from twisted.internet.interfaces import (
    IAddress, IConnector, IResolverSimple, IReactorTCP, IReactorSSL,
    IReactorWin32Events, IReactorUDP, IReactorMulticast, IReactorProcess,
    IReactorTime, IDelayedCall, IReactorThreads, IReactorCore,
    IReactorPluggableResolver, IReactorDaemonize, IReactorFDSet,
    IListeningPort, ILoggingContext, IFileDescriptor, IReadDescriptor,
    IWriteDescriptor, IReadWriteDescriptor, IHalfCloseableDescriptor,
    ISystemHandle, IConsumer, IProducer, IPushProducer, IPullProducer,
    IProtocol, IProcessProtocol, IHalfCloseableProtocol,
    IFileDescriptorReceiver, IProtocolFactory, ITransport, ITCPTransport,
    IUNIXTransport,
    ITLSTransport, ISSLTransport, IProcessTransport, IServiceCollection,
    IUDPTransport, IUNIXDatagramTransport, IUNIXDatagramConnectedTransport,
    IMulticastTransport, IStreamClientEndpoint, IStreamServerEndpoint,
    IStreamServerEndpointStringParser, IStreamClientEndpointStringParser,
    IReactorUNIX, IReactorUNIXDatagram, IReactorSocket, IResolver
)
