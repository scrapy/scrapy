from twisted.internet.defer import Deferred


def twisted_sleep(seconds):
    from twisted.internet import reactor

    d = Deferred()
    reactor.callLater(seconds, d.callback, None)
    return d
