def install_asyncio_reactor():
    """ Tries to install AsyncioSelectorReactor
    """
    try:
        import asyncio
        from twisted.internet import asyncioreactor
    except ImportError:
        pass
    else:
        from twisted.internet.error import ReactorAlreadyInstalledError
        try:
            asyncioreactor.install(asyncio.get_event_loop())
        except ReactorAlreadyInstalledError:
            pass


def is_asyncio_supported():
    try:
        import twisted.internet.reactor
        from twisted.internet import asyncioreactor
        return isinstance(twisted.internet.reactor, asyncioreactor.AsyncioSelectorReactor)
    except ImportError:
        return False
