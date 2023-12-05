# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
The reactor is the Twisted event loop within Twisted, the loop which drives
applications using Twisted. The reactor provides APIs for networking,
threading, dispatching events, and more.

The default reactor depends on the platform and will be installed if this
module is imported without another reactor being explicitly installed
beforehand. Regardless of which reactor is installed, importing this module is
the correct way to get a reference to it.

New application code should prefer to pass and accept the reactor as a
parameter where it is needed, rather than relying on being able to import this
module to get a reference.  This simplifies unit testing and may make it easier
to one day support multiple reactors (as a performance enhancement), though
this is not currently possible.

@see: L{IReactorCore<twisted.internet.interfaces.IReactorCore>}
@see: L{IReactorTime<twisted.internet.interfaces.IReactorTime>}
@see: L{IReactorProcess<twisted.internet.interfaces.IReactorProcess>}
@see: L{IReactorTCP<twisted.internet.interfaces.IReactorTCP>}
@see: L{IReactorSSL<twisted.internet.interfaces.IReactorSSL>}
@see: L{IReactorUDP<twisted.internet.interfaces.IReactorUDP>}
@see: L{IReactorMulticast<twisted.internet.interfaces.IReactorMulticast>}
@see: L{IReactorUNIX<twisted.internet.interfaces.IReactorUNIX>}
@see: L{IReactorUNIXDatagram<twisted.internet.interfaces.IReactorUNIXDatagram>}
@see: L{IReactorFDSet<twisted.internet.interfaces.IReactorFDSet>}
@see: L{IReactorThreads<twisted.internet.interfaces.IReactorThreads>}
@see: L{IReactorPluggableResolver<twisted.internet.interfaces.IReactorPluggableResolver>}
"""


import sys

del sys.modules["twisted.internet.reactor"]
from twisted.internet import default

default.install()
