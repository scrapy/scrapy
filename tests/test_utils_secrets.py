from __future__ import annotations

import json
import logging
from unittest import mock

import pytest

from scrapy.utils.secrets import _load_dotenv, resolve_secret


class TestResolveSecretPlainValues:
    def test_plain_string(self):
        assert resolve_secret("my-api-key") == "my-api-key"

    def test_empty_string(self):
        assert resolve_secret("") == ""

    def test_integer(self):
        assert resolve_secret(42) == "42"

    def test_float(self):
        assert resolve_secret(3.14) == "3.14"

    def test_bool(self):
        assert resolve_secret(True) == "True"

    def test_json_string_value(self):
        # A JSON-encoded string — returned as-is (the original raw string).
        assert resolve_secret('"json-encoded-string"') == '"json-encoded-string"'

    def test_json_number_value(self):
        assert resolve_secret("123") == "123"

    def test_json_list_value(self):
        assert resolve_secret('["a", "b"]') == '["a", "b"]'

    def test_invalid_json(self):
        assert resolve_secret("not {json}") == "not {json}"

    def test_json_object_no_recognised_key(self):
        # A JSON object that is a literal secret (e.g. a GCP service-account
        # JSON blob) — returned as the original raw string.
        blob = '{"type": "service_account", "project_id": "my-project"}'
        assert resolve_secret(blob) == blob

    def test_dict_no_recognised_key(self):
        # Same but already a Python dict (set programmatically).
        spec = {"type": "service_account", "project_id": "my-project"}
        # raw is None for dict inputs → returned as None (no raw string to fall back to)
        assert resolve_secret(spec) is None


class TestResolveSecretRaw:
    def test_raw_string(self):
        assert resolve_secret('{"raw": "literal-value"}') == "literal-value"

    def test_raw_dict(self):
        inner = {"type": "service_account", "env": "would-be-ambiguous"}
        value = json.dumps({"raw": inner})
        assert resolve_secret(value) == json.dumps(inner)

    def test_raw_list(self):
        value = '{"raw": [1, 2, 3]}'
        assert resolve_secret(value) == "[1, 2, 3]"

    def test_raw_number(self):
        assert resolve_secret('{"raw": 42}') == "42"

    def test_raw_dict_input(self):
        assert resolve_secret({"raw": "secret"}) == "secret"

    def test_raw_dict_inner_dict(self):
        inner = {"key": "value"}
        assert resolve_secret({"raw": inner}) == json.dumps(inner)


class TestResolveSecretEnv:
    def test_env_var_set(self):
        with mock.patch.dict("os.environ", {"MY_SECRET": "s3cr3t"}):
            assert resolve_secret('{"env": "MY_SECRET"}') == "s3cr3t"

    def test_env_var_set_dict_input(self):
        with mock.patch.dict("os.environ", {"MY_SECRET": "s3cr3t"}):
            assert resolve_secret({"env": "MY_SECRET"}) == "s3cr3t"

    def test_env_var_missing_returns_default_none(self, caplog):
        with mock.patch.dict("os.environ", {}, clear=False):
            # ensure the var is absent
            os_env = {
                k: v for k, v in __import__("os").environ.items() if k != "MISSING_VAR"
            }
            with (
                mock.patch.dict("os.environ", os_env, clear=True),
                caplog.at_level(logging.WARNING, logger="scrapy.utils.secrets"),
            ):
                result = resolve_secret('{"env": "MISSING_VAR"}')
        assert result is None
        assert "MISSING_VAR" in caplog.text

    def test_env_var_missing_returns_explicit_default(self, caplog):
        with (
            mock.patch.dict("os.environ", {}, clear=True),
            caplog.at_level(logging.WARNING, logger="scrapy.utils.secrets"),
        ):
            result = resolve_secret('{"env": "MISSING_VAR"}', default="fallback")
        assert result == "fallback"

    def test_env_var_missing_logs_warning(self, caplog):
        with (
            mock.patch.dict("os.environ", {}, clear=True),
            caplog.at_level(logging.WARNING, logger="scrapy.utils.secrets"),
        ):
            resolve_secret('{"env": "ABSENT_VAR"}')
        assert "ABSENT_VAR" in caplog.text
        assert caplog.records[0].levelno == logging.WARNING

    def test_env_var_name_not_string_raises(self):
        with pytest.raises(ValueError, match='"env" must be a string'):
            resolve_secret({"env": 123})


class TestResolveSecretKeyring:
    def test_keyring_string_syntax(self):
        mock_keyring = mock.MagicMock()
        mock_keyring.get_password.return_value = "ring-secret"
        with mock.patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = resolve_secret('{"keyring": "my-account"}')
        assert result == "ring-secret"
        mock_keyring.get_password.assert_called_once_with("scrapy", "my-account")

    def test_keyring_dict_syntax_defaults(self):
        mock_keyring = mock.MagicMock()
        mock_keyring.get_password.return_value = "ring-secret"
        with mock.patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = resolve_secret('{"keyring": {"username": "my-account"}}')
        assert result == "ring-secret"
        mock_keyring.get_password.assert_called_once_with("scrapy", "my-account")

    def test_keyring_dict_syntax_custom_service(self):
        mock_keyring = mock.MagicMock()
        mock_keyring.get_password.return_value = "ring-secret"
        with mock.patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = resolve_secret(
                '{"keyring": {"username": "user", "service": "myapp"}}'
            )
        assert result == "ring-secret"
        mock_keyring.get_password.assert_called_once_with("myapp", "user")

    def test_keyring_dict_syntax_missing_username_raises(self):
        mock_keyring = mock.MagicMock()
        with (
            mock.patch.dict("sys.modules", {"keyring": mock_keyring}),
            pytest.raises((KeyError, ValueError)),
        ):
            resolve_secret('{"keyring": {"service": "myapp"}}')

    def test_keyring_entry_missing_raises(self):
        mock_keyring = mock.MagicMock()
        mock_keyring.get_password.return_value = None
        with (
            mock.patch.dict("sys.modules", {"keyring": mock_keyring}),
            pytest.raises(KeyError, match="scrapy"),
        ):
            resolve_secret('{"keyring": "nonexistent-account"}')

    def test_keyring_not_installed_raises_import_error(self):
        with (
            mock.patch.dict("sys.modules", {"keyring": None}),
            pytest.raises(ImportError, match="keyring"),
        ):
            resolve_secret('{"keyring": "my-account"}')

    def test_keyring_dict_input(self):
        mock_keyring = mock.MagicMock()
        mock_keyring.get_password.return_value = "ring-secret"
        with mock.patch.dict("sys.modules", {"keyring": mock_keyring}):
            result = resolve_secret({"keyring": "my-account"})
        assert result == "ring-secret"

    def test_keyring_invalid_type_raises(self):
        mock_keyring = mock.MagicMock()
        with (
            mock.patch.dict("sys.modules", {"keyring": mock_keyring}),
            pytest.raises(ValueError, match='"keyring" must be'),
        ):
            resolve_secret({"keyring": 42})

    def test_keyring_custom_backend(self):
        mock_backend_cls = mock.MagicMock()
        mock_backend_instance = mock_backend_cls.return_value
        mock_backend_instance.get_password.return_value = "backend-secret"

        mock_keyring = mock.MagicMock()

        with (
            mock.patch.dict("sys.modules", {"keyring": mock_keyring}),
            mock.patch(
                "scrapy.utils.secrets.load_object", return_value=mock_backend_cls
            ),
        ):
            result = resolve_secret(
                {
                    "keyring": {
                        "username": "user",
                        "service": "svc",
                        "backend": "my.module.BackendClass",
                    }
                }
            )
        assert result == "backend-secret"
        mock_backend_instance.get_password.assert_called_once_with("svc", "user")


class TestLoadDotenv:
    def test_missing_dotenv_package_warns(self, tmp_path):
        dotenv_file = tmp_path / ".env"
        dotenv_file.write_text("FOO=bar\n")
        with (
            mock.patch.dict("sys.modules", {"dotenv": None}),
            pytest.warns(UserWarning, match="python-dotenv"),
        ):
            _load_dotenv(path=str(dotenv_file))

    def test_nonexistent_file_is_noop(self, tmp_path):
        # A missing .env file is silently skipped regardless of whether
        # python-dotenv is installed.
        absent = str(tmp_path / "nonexistent.env")
        before = dict(__import__("os").environ)
        _load_dotenv(path=absent)
        assert dict(__import__("os").environ) == before

    @pytest.mark.requires_dotenv
    def test_loads_variables(self, tmp_path):
        dotenv_file = tmp_path / ".env"
        dotenv_file.write_text("SCRAPY_TEST_SECRET_VAR=hello\n")
        with mock.patch.dict("os.environ", {}, clear=False):
            # Remove test var if present
            __import__("os").environ.pop("SCRAPY_TEST_SECRET_VAR", None)
            _load_dotenv(path=str(dotenv_file))
            assert __import__("os").environ.get("SCRAPY_TEST_SECRET_VAR") == "hello"
            __import__("os").environ.pop("SCRAPY_TEST_SECRET_VAR", None)

    @pytest.mark.requires_dotenv
    def test_real_env_wins_over_dotenv(self, tmp_path):
        dotenv_file = tmp_path / ".env"
        dotenv_file.write_text("SCRAPY_TEST_OVERRIDE_VAR=from-file\n")
        with mock.patch.dict(
            "os.environ", {"SCRAPY_TEST_OVERRIDE_VAR": "from-env"}, clear=False
        ):
            _load_dotenv(path=str(dotenv_file), override=False)
            assert __import__("os").environ["SCRAPY_TEST_OVERRIDE_VAR"] == "from-env"

    @pytest.mark.requires_dotenv
    def test_override_true_replaces_env(self, tmp_path):
        dotenv_file = tmp_path / ".env"
        dotenv_file.write_text("SCRAPY_TEST_OVERRIDE_VAR=from-file\n")
        with mock.patch.dict(
            "os.environ", {"SCRAPY_TEST_OVERRIDE_VAR": "from-env"}, clear=False
        ):
            _load_dotenv(path=str(dotenv_file), override=True)
            assert __import__("os").environ["SCRAPY_TEST_OVERRIDE_VAR"] == "from-file"
            __import__("os").environ.pop("SCRAPY_TEST_OVERRIDE_VAR", None)


@pytest.mark.requires_keyring
class TestResolveSecretKeyringIntegration:
    """Integration tests that exercise the real keyring library."""

    def test_get_password_returns_value(self):
        import keyring  # noqa: PLC0415
        import keyring.backend  # noqa: PLC0415
        import keyring.backends.null  # noqa: PLC0415

        class _InMemoryKeyring(keyring.backend.KeyringBackend):
            priority = 1
            _store: dict[tuple[str, str], str] = {}

            def get_password(self, service, username):
                return self._store.get((service, username))

            def set_password(self, service, username, password):
                self._store[(service, username)] = password

            def delete_password(self, service, username):
                self._store.pop((service, username), None)

        backend = _InMemoryKeyring()
        backend.set_password("scrapy", "my-account", "real-secret")
        original = keyring.get_keyring()
        try:
            keyring.set_keyring(backend)
            assert resolve_secret({"keyring": "my-account"}) == "real-secret"
        finally:
            keyring.set_keyring(original)

    def test_missing_entry_raises_key_error(self):
        import keyring  # noqa: PLC0415
        import keyring.backends.null  # noqa: PLC0415

        original = keyring.get_keyring()
        try:
            keyring.set_keyring(keyring.backends.null.Keyring())
            with pytest.raises(KeyError):
                resolve_secret({"keyring": "nonexistent"})
        finally:
            keyring.set_keyring(original)
