import ssl

import pytest

from scrapy.settings import Settings
from scrapy.utils.ssl import (
    _get_cert_options_version_kwargs,
    _get_tls_version_limit,
    _get_tls_version_limits,
    _make_insecure_ssl_ctx,
    _make_ssl_context,
    get_openssl_version,
)

_VERSION_MAP = {
    "TLSv1.0": ssl.TLSVersion.TLSv1,
    "TLSv1.1": ssl.TLSVersion.TLSv1_1,
    "TLSv1.2": ssl.TLSVersion.TLSv1_2,
    "TLSv1.3": ssl.TLSVersion.TLSv1_3,
}


class TestGetTLSVersionLimit:
    def test_returns_none_when_unset(self):
        settings = Settings()  # DOWNLOAD_TLS_MIN_VERSION defaults to None
        assert (
            _get_tls_version_limit(
                settings, "DOWNLOAD_TLS_MIN_VERSION", _VERSION_MAP.__getitem__
            )
            is None
        )

    @pytest.mark.parametrize(("name", "expected"), list(_VERSION_MAP.items()))
    def test_converts_known_value(self, name, expected):
        settings = Settings({"DOWNLOAD_TLS_MIN_VERSION": name})
        assert (
            _get_tls_version_limit(
                settings, "DOWNLOAD_TLS_MIN_VERSION", _VERSION_MAP.__getitem__
            )
            == expected
        )

    def test_unknown_value_raises_value_error(self):
        settings = Settings({"DOWNLOAD_TLS_MIN_VERSION": "TLSv9.9"})
        with pytest.raises(ValueError, match="Unknown DOWNLOAD_TLS_MIN_VERSION value"):
            _get_tls_version_limit(
                settings, "DOWNLOAD_TLS_MIN_VERSION", _VERSION_MAP.__getitem__
            )

    def test_returns_both_limits(self):
        settings = Settings(
            {
                "DOWNLOAD_TLS_MIN_VERSION": "TLSv1.1",
                "DOWNLOAD_TLS_MAX_VERSION": "TLSv1.3",
            }
        )
        low, high = _get_tls_version_limits(settings, _VERSION_MAP.__getitem__)
        assert low == ssl.TLSVersion.TLSv1_1
        assert high == ssl.TLSVersion.TLSv1_3

    def test_converts_max_version_setting(self):
        settings = Settings({"DOWNLOAD_TLS_MAX_VERSION": "TLSv1.3"})
        assert (
            _get_tls_version_limit(
                settings, "DOWNLOAD_TLS_MAX_VERSION", _VERSION_MAP.__getitem__
            )
            == ssl.TLSVersion.TLSv1_3
        )

    def test_both_limits_none_by_default(self):
        low, high = _get_tls_version_limits(Settings(), _VERSION_MAP.__getitem__)
        assert low is None
        assert high is None

    def test_only_min_limit_set(self):
        settings = Settings({"DOWNLOAD_TLS_MIN_VERSION": "TLSv1.2"})
        low, high = _get_tls_version_limits(settings, _VERSION_MAP.__getitem__)
        assert low == ssl.TLSVersion.TLSv1_2
        assert high is None


class TestMakeSSLContext:
    def test_returns_tls_client_context(self):
        ctx = _make_ssl_context(Settings())
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.protocol == ssl.PROTOCOL_TLS_CLIENT

    def test_default_settings_skip_verification(self):
        ctx = _make_ssl_context(Settings())
        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_NONE

    def test_verification_enabled(self):
        ctx = _make_ssl_context(Settings({"DOWNLOAD_VERIFY_CERTIFICATES": True}))
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    @pytest.mark.parametrize(
        ("name", "expected"),
        [("TLSv1.2", ssl.TLSVersion.TLSv1_2), ("TLSv1.3", ssl.TLSVersion.TLSv1_3)],
    )
    def test_minimum_version_applied(self, name, expected):
        ctx = _make_ssl_context(Settings({"DOWNLOAD_TLS_MIN_VERSION": name}))
        assert ctx.minimum_version == expected

    @pytest.mark.parametrize(
        ("name", "expected"),
        [("TLSv1.2", ssl.TLSVersion.TLSv1_2), ("TLSv1.3", ssl.TLSVersion.TLSv1_3)],
    )
    def test_maximum_version_applied(self, name, expected):
        ctx = _make_ssl_context(Settings({"DOWNLOAD_TLS_MAX_VERSION": name}))
        assert ctx.maximum_version == expected

    def test_version_left_at_default_when_unset(self):
        default_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx = _make_ssl_context(Settings())
        assert ctx.minimum_version == default_ctx.minimum_version
        assert ctx.maximum_version == default_ctx.maximum_version

    def test_unknown_version_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown DOWNLOAD_TLS_MIN_VERSION"):
            _make_ssl_context(Settings({"DOWNLOAD_TLS_MIN_VERSION": "bogus"}))

    def test_valid_ciphers_accepted(self):
        ctx = _make_ssl_context(Settings({"DOWNLOADER_CLIENT_TLS_CIPHERS": "DEFAULT"}))
        assert isinstance(ctx, ssl.SSLContext)

    def test_invalid_ciphers_raise_ssl_error(self):
        with pytest.raises(ssl.SSLError):
            _make_ssl_context(
                Settings({"DOWNLOADER_CLIENT_TLS_CIPHERS": "NOT-A-REAL-CIPHER"})
            )

    def test_empty_ciphers_setting_is_skipped(self):
        # An empty string is falsy, so ``set_ciphers`` is not called.
        ctx = _make_ssl_context(Settings({"DOWNLOADER_CLIENT_TLS_CIPHERS": ""}))
        assert isinstance(ctx, ssl.SSLContext)

    def test_min_and_max_versions_together(self):
        ctx = _make_ssl_context(
            Settings(
                {
                    "DOWNLOAD_TLS_MIN_VERSION": "TLSv1.2",
                    "DOWNLOAD_TLS_MAX_VERSION": "TLSv1.3",
                }
            )
        )
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2
        assert ctx.maximum_version == ssl.TLSVersion.TLSv1_3

    def test_verification_and_version_together(self):
        ctx = _make_ssl_context(
            Settings(
                {
                    "DOWNLOAD_VERIFY_CERTIFICATES": True,
                    "DOWNLOAD_TLS_MIN_VERSION": "TLSv1.2",
                }
            )
        )
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2


class TestGetCertOptionsVersionKwargs:
    def test_no_limits_returns_empty_kwargs(self):
        assert _get_cert_options_version_kwargs(None, None) == {}


class TestMakeInsecureSSLContext:
    def test_does_not_verify(self):
        ctx = _make_insecure_ssl_ctx()
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_NONE


class TestGetOpenSSLVersion:
    def test_returns_descriptive_string(self):
        version = get_openssl_version()
        assert isinstance(version, str)
        # Format: "<pyOpenSSL version> (<system OpenSSL build string>)"
        assert "(" in version
        assert version.endswith(")")
