import asyncio
from contextlib import suppress

from twisted.internet import asyncioreactor
from twisted.internet.error import ReactorAlreadyInstalledError


def install_asyncio_reactor():
    """ Tries to install AsyncioSelectorReactor
    """
    with suppress(ReactorAlreadyInstalledError):
        asyncioreactor.install(asyncio.get_event_loop())


def is_asyncio_reactor_installed():
    from twisted.internet import reactor
    return isinstance(reactor, asyncioreactor.AsyncioSelectorReactor)
