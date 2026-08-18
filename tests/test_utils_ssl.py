from __future__ import annotations

import logging
import warnings
from typing import cast
from unittest import mock

import OpenSSL._util as pyOpenSSLutil
import OpenSSL.SSL
import pytest
from OpenSSL import crypto

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.ssl import (
    _log_ssl_conn_debug_info,
    ffi_buf_to_string,
    get_openssl_version,
    get_temp_key_info,
    x509name_to_string,
)


def test_ffi_buf_to_string() -> None:
    buf = pyOpenSSLutil.ffi.new("char[]", b"some text")
    with pytest.warns(
        ScrapyDeprecationWarning, match=r"ffi_buf_to_string\(\) is deprecated"
    ):
        assert ffi_buf_to_string(buf) == "some text"


def test_x509name_to_string() -> None:
    with warnings.catch_warnings():
        # X509 itself is deprecated in pyOpenSSL, but it is the only way to build
        # the X509Name that the deprecated function under test takes.
        warnings.simplefilter("ignore", DeprecationWarning)
        subject = crypto.X509().get_subject()
    subject.C = "IE"
    subject.O = "Scrapy"
    subject.CN = "localhost"
    with pytest.warns(
        ScrapyDeprecationWarning, match=r"x509name_to_string\(\) is deprecated"
    ):
        assert x509name_to_string(subject) == "/C=IE/O=Scrapy/CN=localhost"


def test_get_temp_key_info() -> None:
    with pytest.warns(
        ScrapyDeprecationWarning, match=r"get_temp_key_info\(\) is deprecated"
    ):
        assert get_temp_key_info(object()) is None


def test_get_openssl_version() -> None:
    assert "OpenSSL" in get_openssl_version()


def test_log_ssl_conn_debug_info_no_certificate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    connection = mock.MagicMock()
    connection.get_protocol_version_name.return_value = "TLSv1.3"
    connection.get_cipher_name.return_value = "TLS_AES_256_GCM_SHA384"
    connection.get_peer_certificate.return_value = None
    with caplog.at_level(logging.DEBUG, logger="scrapy.utils.ssl"):
        _log_ssl_conn_debug_info(
            "example.com", cast("OpenSSL.SSL.Connection", connection)
        )
    assert "SSL connection to example.com using protocol TLSv1.3" in caplog.text
    assert "certificate" not in caplog.text
