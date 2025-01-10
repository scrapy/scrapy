import random
from typing import Any
from urllib.parse import urlencode

from twisted.web.resource import Resource
from twisted.web.server import Request, Site


class Root(Resource):
    isLeaf = True

    def getChild(self, name: str, request: Request) -> Resource:
        return self

    def render(self, request: Request) -> bytes:
        total = _getarg(request, b"total", 100, int)
        show = _getarg(request, b"show", 10, int)
        nlist = [random.randint(1, total) for _ in range(show)]  # noqa: S311
        request.write(b"<html><head></head><body>")
        assert request.args is not None
        args = request.args.copy()
        for nl in nlist:
            args["n"] = nl
            argstr = urlencode(args, doseq=True)
            request.write(f"<a href='/follow?{argstr}'>follow {nl}</a><br>".encode())
        request.write(b"</body></html>")
        return b""


def _getarg(request, name: bytes, default: Any = None, type=str):
    return type(request.args[name][0]) if name in request.args else default


if __name__ == "__main__":
    from twisted.internet import reactor

    root = Root()
    factory = Site(root)
    httpPort = reactor.listenTCP(8998, Site(root))

    def _print_listening() -> None:
        httpHost = httpPort.getHost()
        print(f"Bench server at http://{httpHost.host}:{httpHost.port}")

    reactor.callWhenRunning(_print_listening)
    reactor.run()
