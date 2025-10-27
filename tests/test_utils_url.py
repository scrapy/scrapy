import warnings
from importlib import import_module

import pytest

from scrapy.linkextractors import IGNORED_EXTENSIONS
from scrapy.spiders import Spider
from scrapy.utils.url import (  # type: ignore[attr-defined]
    _is_filesystem_path,
    _public_w3lib_objects,
    add_http_if_no_scheme,
    guess_scheme,
    strip_url,
    url_has_any_extension,
    url_is_from_any_domain,
    url_is_from_spider,
)


def test_url_is_from_any_domain():
    url = "http://www.wheele-bin-art.co.uk/get/product/123"
    assert url_is_from_any_domain(url, ["wheele-bin-art.co.uk"])
    assert not url_is_from_any_domain(url, ["art.co.uk"])

    url = "http://wheele-bin-art.co.uk/get/product/123"
    assert url_is_from_any_domain(url, ["wheele-bin-art.co.uk"])
    assert not url_is_from_any_domain(url, ["art.co.uk"])

    url = "http://www.Wheele-Bin-Art.co.uk/get/product/123"
    assert url_is_from_any_domain(url, ["wheele-bin-art.CO.UK"])
    assert url_is_from_any_domain(url, ["WHEELE-BIN-ART.CO.UK"])

    url = "http://192.169.0.15:8080/mypage.html"
    assert url_is_from_any_domain(url, ["192.169.0.15:8080"])
    assert not url_is_from_any_domain(url, ["192.169.0.15"])

    url = (
        "javascript:%20document.orderform_2581_1190810811.mode.value=%27add%27;%20"
        "javascript:%20document.orderform_2581_1190810811.submit%28%29"
    )
    assert not url_is_from_any_domain(url, ["testdomain.com"])
    assert not url_is_from_any_domain(url + ".testdomain.com", ["testdomain.com"])


def test_url_is_from_spider():
    class MySpider(Spider):
        name = "example.com"

    assert url_is_from_spider("http://www.example.com/some/page.html", MySpider)
    assert url_is_from_spider("http://sub.example.com/some/page.html", MySpider)
    assert not url_is_from_spider("http://www.example.org/some/page.html", MySpider)
    assert not url_is_from_spider("http://www.example.net/some/page.html", MySpider)


def test_url_is_from_spider_class_attributes():
    class MySpider(Spider):
        name = "example.com"

    assert url_is_from_spider("http://www.example.com/some/page.html", MySpider)
    assert url_is_from_spider("http://sub.example.com/some/page.html", MySpider)
    assert not url_is_from_spider("http://www.example.org/some/page.html", MySpider)
    assert not url_is_from_spider("http://www.example.net/some/page.html", MySpider)


def test_url_is_from_spider_with_allowed_domains():
    class MySpider(Spider):
        name = "example.com"
        allowed_domains = ["example.org", "example.net"]

    assert url_is_from_spider("http://www.example.com/some/page.html", MySpider)
    assert url_is_from_spider("http://sub.example.com/some/page.html", MySpider)
    assert url_is_from_spider("http://example.com/some/page.html", MySpider)
    assert url_is_from_spider("http://www.example.org/some/page.html", MySpider)
    assert url_is_from_spider("http://www.example.net/some/page.html", MySpider)
    assert not url_is_from_spider("http://www.example.us/some/page.html", MySpider)

    class MySpider2(Spider):
        name = "example.com"
        allowed_domains = {"example.com", "example.net"}

    assert url_is_from_spider("http://www.example.com/some/page.html", MySpider2)

    class MySpider3(Spider):
        name = "example.com"
        allowed_domains = ("example.com", "example.net")

    assert url_is_from_spider("http://www.example.com/some/page.html", MySpider3)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://www.example.com/archive.tar.gz", True),
        ("http://www.example.com/page.doc", True),
        ("http://www.example.com/page.pdf", True),
        ("http://www.example.com/page.htm", False),
        ("http://www.example.com/", False),
        ("http://www.example.com/page.doc.html", False),
    ],
)
def test_url_has_any_extension(url: str, expected: bool) -> None:
    deny_extensions = {"." + e for e in IGNORED_EXTENSIONS}
    assert url_has_any_extension(url, deny_extensions) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("www.example.com", "http://www.example.com"),
        ("example.com", "http://example.com"),
        ("www.example.com/some/page.html", "http://www.example.com/some/page.html"),
        ("www.example.com:80", "http://www.example.com:80"),
        ("www.example.com/some/page#frag", "http://www.example.com/some/page#frag"),
        ("www.example.com/do?a=1&b=2&c=3", "http://www.example.com/do?a=1&b=2&c=3"),
        (
            "username:password@www.example.com",
            "http://username:password@www.example.com",
        ),
        (
            "username:password@www.example.com:80/some/page/do?a=1&b=2&c=3#frag",
            "http://username:password@www.example.com:80/some/page/do?a=1&b=2&c=3#frag",
        ),
        ("http://www.example.com", "http://www.example.com"),
        ("http://example.com", "http://example.com"),
        (
            "http://www.example.com/some/page.html",
            "http://www.example.com/some/page.html",
        ),
        ("http://www.example.com:80", "http://www.example.com:80"),
        (
            "http://www.example.com/some/page#frag",
            "http://www.example.com/some/page#frag",
        ),
        (
            "http://www.example.com/do?a=1&b=2&c=3",
            "http://www.example.com/do?a=1&b=2&c=3",
        ),
        (
            "http://username:password@www.example.com",
            "http://username:password@www.example.com",
        ),
        (
            "http://username:password@www.example.com:80/some/page/do?a=1&b=2&c=3#frag",
            "http://username:password@www.example.com:80/some/page/do?a=1&b=2&c=3#frag",
        ),
        ("//www.example.com", "http://www.example.com"),
        ("//example.com", "http://example.com"),
        ("//www.example.com/some/page.html", "http://www.example.com/some/page.html"),
        ("//www.example.com:80", "http://www.example.com:80"),
        ("//www.example.com/some/page#frag", "http://www.example.com/some/page#frag"),
        ("//www.example.com/do?a=1&b=2&c=3", "http://www.example.com/do?a=1&b=2&c=3"),
        (
            "//username:password@www.example.com",
            "http://username:password@www.example.com",
        ),
        (
            "//username:password@www.example.com:80/some/page/do?a=1&b=2&c=3#frag",
            "http://username:password@www.example.com:80/some/page/do?a=1&b=2&c=3#frag",
        ),
        ("https://www.example.com", "https://www.example.com"),
        ("ftp://www.example.com", "ftp://www.example.com"),
    ],
)
def test_add_http_if_no_scheme(url: str, expected: str) -> None:
    assert add_http_if_no_scheme(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("/index", "file://"),
        ("/index.html", "file://"),
        ("./index.html", "file://"),
        ("../index.html", "file://"),
        ("../../index.html", "file://"),
        ("./data/index.html", "file://"),
        (".hidden/data/index.html", "file://"),
        ("/home/user/www/index.html", "file://"),
        ("//home/user/www/index.html", "file://"),
        ("file:///home/user/www/index.html", "file://"),
        ("index.html", "http://"),
        ("example.com", "http://"),
        ("www.example.com", "http://"),
        ("www.example.com/index.html", "http://"),
        ("http://example.com", "http://"),
        ("http://example.com/index.html", "http://"),
        ("localhost", "http://"),
        ("localhost/index.html", "http://"),
        # some corner cases (default to http://)
        ("/", "http://"),
        (".../test", "http://"),
    ],
)
def test_guess_scheme(url: str, expected: str):
    assert guess_scheme(url).startswith(expected)


@pytest.mark.parametrize(
    ("url", "expected", "reason"),
    [
        (
            r"C:\absolute\path\to\a\file.html",
            "file://",
            "Windows filepath are not supported for scrapy shell",
        ),
    ],
)
def test_guess_scheme_skipped(url: str, expected: str, reason: str):
    pytest.skip(reason)


class TestStripUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "http://www.example.com/index.html",
            "http://www.example.com/index.html?somekey=somevalue",
        ],
    )
    def test_noop(self, url: str) -> None:
        assert strip_url(url) == url

    def test_fragments(self):
        assert (
            strip_url(
                "http://www.example.com/index.html?somekey=somevalue#section",
                strip_fragment=False,
            )
            == "http://www.example.com/index.html?somekey=somevalue#section"
        )

    @pytest.mark.parametrize(
        ("url", "origin", "expected"),
        [
            ("http://www.example.com/", False, "http://www.example.com/"),
            ("http://www.example.com", False, "http://www.example.com"),
            ("http://www.example.com", True, "http://www.example.com/"),
        ],
    )
    def test_path(self, url: str, origin: bool, expected: str) -> None:
        assert strip_url(url, origin_only=origin) == expected

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            (
                "http://username@www.example.com/index.html?somekey=somevalue#section",
                "http://www.example.com/index.html?somekey=somevalue",
            ),
            (
                "https://username:@www.example.com/index.html?somekey=somevalue#section",
                "https://www.example.com/index.html?somekey=somevalue",
            ),
            (
                "ftp://username:password@www.example.com/index.html?somekey=somevalue#section",
                "ftp://www.example.com/index.html?somekey=somevalue",
            ),
            # user: "username@", password: none
            (
                "http://username%40@www.example.com/index.html?somekey=somevalue#section",
                "http://www.example.com/index.html?somekey=somevalue",
            ),
            # user: "username:pass", password: ""
            (
                "https://username%3Apass:@www.example.com/index.html?somekey=somevalue#section",
                "https://www.example.com/index.html?somekey=somevalue",
            ),
            # user: "me", password: "user@domain.com"
            (
                "ftp://me:user%40domain.com@www.example.com/index.html?somekey=somevalue#section",
                "ftp://www.example.com/index.html?somekey=somevalue",
            ),
        ],
    )
    def test_credentials(self, url: str, expected: str) -> None:
        assert strip_url(url, strip_credentials=True) == expected

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            (
                "http://username:password@www.example.com:80/index.html?somekey=somevalue#section",
                "http://www.example.com/index.html?somekey=somevalue",
            ),
            (
                "http://username:password@www.example.com:8080/index.html#section",
                "http://www.example.com:8080/index.html",
            ),
            (
                "http://username:password@www.example.com:443/index.html?somekey=somevalue&someotherkey=sov#section",
                "http://www.example.com:443/index.html?somekey=somevalue&someotherkey=sov",
            ),
            (
                "https://username:password@www.example.com:443/index.html",
                "https://www.example.com/index.html",
            ),
            (
                "https://username:password@www.example.com:442/index.html",
                "https://www.example.com:442/index.html",
            ),
            (
                "https://username:password@www.example.com:80/index.html",
                "https://www.example.com:80/index.html",
            ),
            (
                "ftp://username:password@www.example.com:21/file.txt",
                "ftp://www.example.com/file.txt",
            ),
            (
                "ftp://username:password@www.example.com:221/file.txt",
                "ftp://www.example.com:221/file.txt",
            ),
        ],
    )
    def test_default_ports_creds_off(self, url: str, expected: str) -> None:
        assert strip_url(url) == expected

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            (
                "http://username:password@www.example.com:80/index.html",
                "http://username:password@www.example.com/index.html",
            ),
            (
                "http://username:password@www.example.com:8080/index.html",
                "http://username:password@www.example.com:8080/index.html",
            ),
            (
                "http://username:password@www.example.com:443/index.html",
                "http://username:password@www.example.com:443/index.html",
            ),
            (
                "https://username:password@www.example.com:443/index.html",
                "https://username:password@www.example.com/index.html",
            ),
            (
                "https://username:password@www.example.com:442/index.html",
                "https://username:password@www.example.com:442/index.html",
            ),
            (
                "https://username:password@www.example.com:80/index.html",
                "https://username:password@www.example.com:80/index.html",
            ),
            (
                "ftp://username:password@www.example.com:21/file.txt",
                "ftp://username:password@www.example.com/file.txt",
            ),
            (
                "ftp://username:password@www.example.com:221/file.txt",
                "ftp://username:password@www.example.com:221/file.txt",
            ),
        ],
    )
    def test_default_ports(self, url: str, expected: str) -> None:
        assert (
            strip_url(url, strip_default_port=True, strip_credentials=False) == expected
        )

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            (
                "http://username:password@www.example.com:80/index.html?somekey=somevalue&someotherkey=sov#section",
                "http://username:password@www.example.com:80/index.html?somekey=somevalue&someotherkey=sov",
            ),
            (
                "http://username:password@www.example.com:8080/index.html?somekey=somevalue&someotherkey=sov#section",
                "http://username:password@www.example.com:8080/index.html?somekey=somevalue&someotherkey=sov",
            ),
            (
                "http://username:password@www.example.com:443/index.html",
                "http://username:password@www.example.com:443/index.html",
            ),
            (
                "https://username:password@www.example.com:443/index.html",
                "https://username:password@www.example.com:443/index.html",
            ),
            (
                "https://username:password@www.example.com:442/index.html",
                "https://username:password@www.example.com:442/index.html",
            ),
            (
                "https://username:password@www.example.com:80/index.html",
                "https://username:password@www.example.com:80/index.html",
            ),
            (
                "ftp://username:password@www.example.com:21/file.txt",
                "ftp://username:password@www.example.com:21/file.txt",
            ),
            (
                "ftp://username:password@www.example.com:221/file.txt",
                "ftp://username:password@www.example.com:221/file.txt",
            ),
        ],
    )
    def test_default_ports_keep(self, url: str, expected: str) -> None:
        assert (
            strip_url(url, strip_default_port=False, strip_credentials=False)
            == expected
        )

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            (
                "http://username:password@www.example.com/index.html",
                "http://www.example.com/",
            ),
            (
                "http://username:password@www.example.com:80/foo/bar?query=value#somefrag",
                "http://www.example.com/",
            ),
            (
                "http://username:password@www.example.com:8008/foo/bar?query=value#somefrag",
                "http://www.example.com:8008/",
            ),
            (
                "https://username:password@www.example.com:443/index.html",
                "https://www.example.com/",
            ),
        ],
    )
    def test_origin_only(self, url: str, expected: str) -> None:
        assert strip_url(url, origin_only=True) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        # https://en.wikipedia.org/wiki/Path_(computing)#Representations_of_paths_by_operating_system_and_shell
        # Unix-like OS, Microsoft Windows / cmd.exe
        ("/home/user/docs/Letter.txt", True),
        ("./inthisdir", True),
        ("../../greatgrandparent", True),
        ("~/.rcinfo", True),
        (r"C:\user\docs\Letter.txt", True),
        ("/user/docs/Letter.txt", True),
        (r"C:\Letter.txt", True),
        (r"\\Server01\user\docs\Letter.txt", True),
        (r"\\?\UNC\Server01\user\docs\Letter.txt", True),
        (r"\\?\C:\user\docs\Letter.txt", True),
        (r"C:\user\docs\somefile.ext:alternate_stream_name", True),
        (r"https://example.com", False),
    ],
)
def test__is_filesystem_path(path: str, expected: bool) -> None:
    assert _is_filesystem_path(path) == expected


@pytest.mark.parametrize(
    "obj_name",
    [
        "_unquotepath",
        "_safe_chars",
        "parse_url",
        *_public_w3lib_objects,
    ],
)
def test_deprecated_imports_from_w3lib(obj_name: str) -> None:
    with warnings.catch_warnings(record=True) as warns:
        obj_type = "attribute" if obj_name == "_safe_chars" else "function"
        message = f"The scrapy.utils.url.{obj_name} {obj_type} is deprecated, use w3lib.url.{obj_name} instead."

        getattr(import_module("scrapy.utils.url"), obj_name)

        assert isinstance(warns[0].message, Warning)
        assert message in warns[0].message.args
