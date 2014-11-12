import random
from six.moves.urllib.parse import urlencode
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.internet import reactor


class Root(Resource):

    isLeaf = True

    def getChild(self, name, request):
        return self

    def render(self, request):
        total = _getarg(request, 'total', 100, int)
        show = _getarg(request, 'show', 10, int)
        nlist = [random.randint(1, total) for _ in range(show)]
        request.write("<html><head></head><body>")
        args = request.args.copy()
        for nl in nlist:
            args['n'] = nl
            argstr = urlencode(args, doseq=True)
            request.write("<a href='/follow?{0}'>follow {1}</a><br>"
                          .format(argstr, nl))
        request.write("</body></html>")
        return ''


def _getarg(request, name, default=None, type=str):
    return type(request.args[name][0]) \
        if name in request.args else default


if __name__ == '__main__':
    root = Root()
    factory = Site(root)
    httpPort = reactor.listenTCP(8998, Site(root))

    def _print_listening():
        httpHost = httpPort.getHost()
        print("Bench server at http://{}:{}".format(httpHost.host, httpHost.port))
    reactor.callWhenRunning(_print_listening)
    reactor.run()
