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


def _getarg(request, name: bytes, default: Any = None, type_=str):
    """Extract and convert an argument from the request.

    Retrieves the first value of a named argument from the request and
    converts it to the specified type. Returns a default value if the
    argument is not present in the request.

    Args:
        request: The HTTP request object
        name: The argument name to retrieve (as bytes)
        default: Value to return if argument is not found (default: None)
        type_: Callable to convert the argument value (default: str)

    Returns:
        The converted argument value if present, otherwise the default value
    """
    return type_(request.args[name][0]) if name in request.args else default


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
