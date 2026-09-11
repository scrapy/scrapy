from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast
from unittest import mock

from scrapy.utils._ssl import _log_ssl_conn_debug_info

if TYPE_CHECKING:
    import OpenSSL.SSL
    import pytest


def test_log_ssl_conn_debug_info_no_certificate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    connection = mock.MagicMock()
    connection.get_protocol_version_name.return_value = "TLSv1.3"
    connection.get_cipher_name.return_value = "TLS_AES_256_GCM_SHA384"
    connection.get_peer_certificate.return_value = None
    with caplog.at_level(logging.DEBUG, logger="scrapy.utils._ssl"):
        _log_ssl_conn_debug_info(
            "example.com", cast("OpenSSL.SSL.Connection", connection)
        )
    assert "SSL connection to example.com using protocol TLSv1.3" in caplog.text
    assert "certificate" not in caplog.text
