from twisted.internet import reactor, error

def listen_tcp(portrange, factory):
    """Like reactor.listenTCP but tries different ports in a range."""
    assert len(portrange) in [1, 2], "invalid portrange: %s" % portrange
    if not hasattr(portrange, '__iter__'):
        return reactor.listenTCP(portrange, factory)
    if len(portrange) == 1:
        return reactor.listenTCP(portrange[0], factory)
    for x in range(portrange[0], portrange[1]+1):
        try:
            return reactor.listenTCP(x, factory)
        except error.CannotListenError:
            if x == portrange[1]:
                raise
