# This is only used by tests.test_downloader_handlers_http_base.TestSimpleHttpsBase

from __future__ import annotations

from twisted.web import resource
from twisted.web.static import Data

from .http_base import BaseMockServer, main_factory


class Root(resource.Resource):
    def __init__(self):
        resource.Resource.__init__(self)
        self.putChild(b"file", Data(b"0123456789", "text/plain"))

    def getChild(self, name, request):
        return self


class SimpleMockServer(BaseMockServer):
    listen_http = False
    module_name = "tests.mockserver.simple_https"

    def __init__(self, keyfile: str, certfile: str, cipher_string: str | None):
        super().__init__()
        self.keyfile = keyfile
        self.certfile = certfile
        self.cipher_string = cipher_string or ""

    def get_additional_args(self) -> list[str]:
        args = [
            "--keyfile",
            self.keyfile,
            "--certfile",
            self.certfile,
        ]
        if self.cipher_string is not None:
            args.extend(["--cipher-string", self.cipher_string])
        return args


main = main_factory(Root, listen_http=False)


if __name__ == "__main__":
    main()
