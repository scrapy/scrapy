# This is only used by tests.test_downloadermiddleware_robotstxt

from __future__ import annotations

from twisted.web import resource

from .http_base import BaseMockServer, main_factory


class Root(resource.Resource):
    def getChild(self, path, request):
        return self

    def render_GET(self, request):
        if request.path == b"/robots.txt":
            return b"User-agent: *\nDisallow: /deny\n"
        return b"foo"


class RobotsTxtMockServer(BaseMockServer):
    listen_https = False
    module_name = "tests.mockserver.robotstxt"


main = main_factory(Root, listen_https=False)


if __name__ == "__main__":
    main()
