from twisted.internet import defer
from twisted.trial import unittest

from tests.utils.testproc import ProcessTest
from tests.utils.testsite import SiteTest


class TestFetchCommand(ProcessTest, SiteTest, unittest.TestCase):
    command = "fetch"

    @defer.inlineCallbacks
    def test_output(self):
        _, out, _ = yield self.execute([self.url("/text")])
        assert out.strip() == b"Works"

    @defer.inlineCallbacks
    def test_redirect_default(self):
        _, out, _ = yield self.execute([self.url("/redirect")])
        assert out.strip() == b"Redirected here"

    @defer.inlineCallbacks
    def test_redirect_disabled(self):
        _, out, err = yield self.execute(
            ["--no-redirect", self.url("/redirect-no-meta-refresh")]
        )
        err = err.strip()
        assert b"downloader/response_status_count/302" in err, err
        assert b"downloader/response_status_count/200" not in err, err

    @defer.inlineCallbacks
    def test_headers(self):
        _, out, _ = yield self.execute([self.url("/text"), "--headers"])
        out = out.replace(b"\r", b"")  # required on win32
        assert b"Server: TwistedWeb" in out, out
        assert b"Content-Type: text/plain" in out
