# This is only used by tests.test_downloader_handlers_http_base.TestHttpProxyBase

from __future__ import annotations

from .http_base import BaseMockServer, main_factory
from .http_resources import UriResource


class ProxyEchoMockServer(BaseMockServer):
    module_name = "tests.mockserver.proxy_echo"


main = main_factory(UriResource)


if __name__ == "__main__":
    main()
