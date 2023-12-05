# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Test L{twisted.web.pages}
"""

from typing import cast

from twisted.trial.unittest import SynchronousTestCase
from twisted.web.http_headers import Headers
from twisted.web.iweb import IRequest
from twisted.web.pages import errorPage, forbidden, notFound
from twisted.web.resource import IResource
from twisted.web.test.requesthelper import DummyRequest


def _render(resource: IResource) -> DummyRequest:
    """
    Render a response using the given resource.

    @param resource: The resource to use to handle the request.

    @returns: The request that the resource handled,
    """
    request = DummyRequest([b""])
    # The cast is necessary because DummyRequest isn't annotated
    # as an IRequest, and this can't be trivially done. See
    # https://github.com/twisted/twisted/issues/11719
    resource.render(cast(IRequest, request))
    return request


class ErrorPageTests(SynchronousTestCase):
    """
    Test L{twisted.web.pages._ErrorPage} and its public aliases L{errorPage},
    L{notFound} and L{forbidden}.
    """

    maxDiff = None

    def assertResponse(self, request: DummyRequest, code: int, body: bytes) -> None:
        self.assertEqual(request.responseCode, code)
        self.assertEqual(
            request.responseHeaders,
            Headers({b"content-type": [b"text/html; charset=utf-8"]}),
        )
        self.assertEqual(
            # Decode to str because unittest somehow still doesn't diff bytes
            # without truncating them in 2022.
            b"".join(request.written).decode("latin-1"),
            body.decode("latin-1"),
        )

    def test_escapesHTML(self):
        """
        The I{brief} and I{detail} parameters are HTML-escaped on render.
        """
        self.assertResponse(
            _render(errorPage(400, "A & B", "<script>alert('oops!')")),
            400,
            (
                b"<!DOCTYPE html>\n"
                b"<html><head><title>400 - A &amp; B</title></head>"
                b"<body><h1>A &amp; B</h1><p>&lt;script&gt;alert('oops!')"
                b"</p></body></html>"
            ),
        )

    def test_getChild(self):
        """
        The C{getChild} method of the resource returned by L{errorPage} returns
        the L{_ErrorPage} it is called on.
        """
        page = errorPage(404, "foo", "bar")
        self.assertIs(
            page.getChild(b"name", DummyRequest([b""])),
            page,
        )

    def test_notFoundDefaults(self):
        """
        The default arguments to L{twisted.web.pages.notFound} produce
        a reasonable error page.
        """
        self.assertResponse(
            _render(notFound()),
            404,
            (
                b"<!DOCTYPE html>\n"
                b"<html><head><title>404 - No Such Resource</title></head>"
                b"<body><h1>No Such Resource</h1>"
                b"<p>Sorry. No luck finding that resource.</p>"
                b"</body></html>"
            ),
        )

    def test_forbiddenDefaults(self):
        """
        The default arguments to L{twisted.web.pages.forbidden} produce
        a reasonable error page.
        """
        self.assertResponse(
            _render(forbidden()),
            403,
            (
                b"<!DOCTYPE html>\n"
                b"<html><head><title>403 - Forbidden Resource</title></head>"
                b"<body><h1>Forbidden Resource</h1>"
                b"<p>Sorry, resource is forbidden.</p>"
                b"</body></html>"
            ),
        )
