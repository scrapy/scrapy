from gzip import BadGzipFile
from pathlib import Path

import pytest
from w3lib.encoding import html_to_unicode

from scrapy.http import Response
from scrapy.utils.gz import gunzip, gzip_magic_number
from tests import tests_datadir

SAMPLEDIR = Path(tests_datadir, "compressed")


class TestGunzip:
    def test_gunzip_basic(self):
        r1 = Response(
            "http://www.example.com",
            body=(SAMPLEDIR / "feed-sample1.xml.gz").read_bytes(),
        )
        assert gzip_magic_number(r1)

        r2 = Response("http://www.example.com", body=gunzip(r1.body))
        assert not gzip_magic_number(r2)
        assert len(r2.body) == 9950

    def test_gunzip_truncated(self):
        text = gunzip((SAMPLEDIR / "truncated-crc-error.gz").read_bytes())
        assert text.endswith(b"</html")

    def test_gunzip_no_gzip_file_raises(self):
        with pytest.raises(BadGzipFile):
            gunzip((SAMPLEDIR / "feed-sample1.xml").read_bytes())

    def test_gunzip_truncated_short(self):
        r1 = Response(
            "http://www.example.com",
            body=(SAMPLEDIR / "truncated-crc-error-short.gz").read_bytes(),
        )
        assert gzip_magic_number(r1)

        r2 = Response("http://www.example.com", body=gunzip(r1.body))
        assert r2.body.endswith(b"</html>")
        assert not gzip_magic_number(r2)

    def test_is_gzipped_empty(self):
        r1 = Response("http://www.example.com")
        assert not gzip_magic_number(r1)

    def test_gunzip_illegal_eof(self):
        text = html_to_unicode(
            "charset=cp1252", gunzip((SAMPLEDIR / "unexpected-eof.gz").read_bytes())
        )[1]
        expected_text = (SAMPLEDIR / "unexpected-eof-output.txt").read_text(
            encoding="utf-8"
        )
        assert len(text) == len(expected_text)
        assert text == expected_text
