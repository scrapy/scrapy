from tests.mockserver import MockServer
from tests.test_commands import TestProjectBase


class TestFetchCommand(TestProjectBase):
    @classmethod
    def setup_class(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def teardown_class(cls):
        cls.mockserver.__exit__(None, None, None)

    def test_output(self):
        _, out, _ = self.proc("fetch", self.mockserver.url("/text"))
        assert out.strip() == "Works"

    def test_redirect_default(self):
        _, out, _ = self.proc("fetch", self.mockserver.url("/redirect"))
        assert out.strip() == "Redirected here"

    def test_redirect_disabled(self):
        _, _, err = self.proc(
            "fetch", "--no-redirect", self.mockserver.url("/redirect-no-meta-refresh")
        )
        err = err.strip()
        assert "downloader/response_status_count/302" in err, err
        assert "downloader/response_status_count/200" not in err, err

    def test_headers(self):
        _, out, _ = self.proc("fetch", self.mockserver.url("/text"), "--headers")
        out = out.replace("\r", "")  # required on win32
        assert "Server: TwistedWeb" in out, out
        assert "Content-Type: text/plain" in out
