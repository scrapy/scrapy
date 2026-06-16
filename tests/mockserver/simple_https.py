# This is only used by tests.test_downloader_handlers_http_base.TestSimpleHttpsBase

from __future__ import annotations

from twisted.web import resource
from twisted.web.static import Data

from .http_base import BaseMockServer, main_factory


class Root(resource.Resource):
    def __init__(self):
        resource.Resource.__init__(self)
        self.putChild(b"file", Data(b"0123456789", "text/plain"))

    def getChild(self, path, request):
        return self


class SimpleMockServer(BaseMockServer):
    listen_http = False
    module_name = "tests.mockserver.simple_https"

    def __init__(
        self,
        keyfile: str,
        certfile: str,
        *,
        cipher_string: str | None = None,
        tls_min_version: str | None = None,
        tls_max_version: str | None = None,
    ):
        super().__init__()
        self.keyfile = keyfile
        self.certfile = certfile
        self.cipher_string = cipher_string
        self.tls_min_version = tls_min_version
        self.tls_max_version = tls_max_version

    def get_additional_args(self) -> list[str]:
        args = [
            "--keyfile",
            self.keyfile,
            "--certfile",
            self.certfile,
        ]
        if self.cipher_string is not None:
            args.extend(["--cipher-string", self.cipher_string])
        if self.tls_min_version is not None:
            args.extend(["--tls-min-version", self.tls_min_version])
        if self.tls_max_version is not None:
            args.extend(["--tls-max-version", self.tls_max_version])
        return args


main = main_factory(Root, listen_http=False)


if __name__ == "__main__":
    main()
