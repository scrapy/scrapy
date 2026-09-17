from scrapy.utils._versions import _get_openssl_version


def test_get_openssl_version() -> None:
    assert "OpenSSL" in _get_openssl_version()
