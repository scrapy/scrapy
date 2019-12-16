from contextlib import suppress

from twisted.internet.error import ReactorAlreadyInstalledError


def install_asyncio_reactor():
    """ Tries to install AsyncioSelectorReactor
    """
    try:
        import asyncio
        from twisted.internet import asyncioreactor
    except ImportError:
        return

    with suppress(ReactorAlreadyInstalledError):
        asyncioreactor.install(asyncio.get_event_loop())


def is_asyncio_reactor_installed():
    try:
        import twisted.internet.reactor
        from twisted.internet import asyncioreactor
        return isinstance(twisted.internet.reactor, asyncioreactor.AsyncioSelectorReactor)
    except ImportError:
        return False
