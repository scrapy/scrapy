from urllib.parse import urlparse


class TestUrlparse:
    def test_s3_url(self):
        p = urlparse("s3://bucket/key/name?param=value")
        assert p.scheme == "s3"
        assert p.hostname == "bucket"
        assert p.path == "/key/name"
        assert p.query == "param=value"
