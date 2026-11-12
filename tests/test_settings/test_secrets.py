from __future__ import annotations

import sys
from typing import Any

import pytest

from scrapy.settings import BaseSettings


class _InMemoryKeyring:
    passwords = {("myservice", "myuser"): "backend-secret"}

    def get_password(self, service: str, username: str) -> str | None:
        return self.passwords.get((service, username))


def _getsecret(value: Any, default: str | None = None) -> str | None:
    return BaseSettings({"SECRET": value}).getsecret("SECRET", default)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("my-api-key", "my-api-key"),
        ("", ""),
        (42, "42"),
        ('"json-string"', '"json-string"'),
        ('["a", "b"]', '["a", "b"]'),
        ("not {json}", "not {json}"),
        ('{"type": "service_account"}', '{"type": "service_account"}'),
        ('{"raw": "literal"}', "literal"),
        ({"raw": "literal"}, "literal"),
        ('{"raw": {"env": "production"}}', '{"env": "production"}'),
        ({"raw": [1, 2]}, "[1, 2]"),
    ],
)
def test_literal(value: Any, expected: str) -> None:
    assert _getsecret(value) == expected


@pytest.mark.parametrize(("default", "expected"), [(None, None), ("foo", "foo")])
def test_unset(default: str | None, expected: str | None) -> None:
    assert BaseSettings().getsecret("SECRET", default) == expected
    assert _getsecret(None, default) == expected


@pytest.mark.parametrize("value", ['{"env": "MY_SECRET"}', {"env": "MY_SECRET"}])
def test_env(value: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_SECRET", "s3cr3t")
    assert _getsecret(value, "default") == "s3cr3t"


def test_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MY_SECRET", raising=False)
    with pytest.raises(KeyError, match="MY_SECRET"):
        _getsecret({"env": "MY_SECRET"}, "default")


def test_unknown_reference() -> None:
    with pytest.raises(ValueError, match="env, keyring, raw"):
        _getsecret({"type": "service_account"})


@pytest.mark.requires_keyring
@pytest.mark.parametrize(
    ("value", "service", "username"),
    [
        ('{"keyring": "myuser"}', "scrapy", "myuser"),
        ({"keyring": {"username": "myuser"}}, "scrapy", "myuser"),
        (
            {"keyring": {"username": "myuser", "service": "myservice"}},
            "myservice",
            "myuser",
        ),
    ],
)
def test_keyring(
    value: Any, service: str, username: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import keyring  # noqa: PLC0415

    calls = []

    def get_password(service: str, username: str) -> str:
        calls.append((service, username))
        return "keyring-secret"

    monkeypatch.setattr(keyring, "get_password", get_password)
    assert _getsecret(value) == "keyring-secret"
    assert calls == [(service, username)]


@pytest.mark.requires_keyring
def test_keyring_backend() -> None:
    value = {
        "keyring": {
            "username": "myuser",
            "service": "myservice",
            "backend": f"{__name__}._InMemoryKeyring",
        }
    }
    assert _getsecret(value) == "backend-secret"


@pytest.mark.requires_keyring
def test_keyring_missing() -> None:
    import keyring  # noqa: PLC0415
    from keyring.backends.null import Keyring  # noqa: PLC0415

    original = keyring.get_keyring()
    keyring.set_keyring(Keyring())
    try:
        with pytest.raises(KeyError, match="myuser"):
            _getsecret({"keyring": "myuser"})
    finally:
        keyring.set_keyring(original)


@pytest.mark.requires_keyring
@pytest.mark.parametrize(
    ("value", "match"),
    [
        ({"keyring": 42}, '"keyring" must be'),
        ({"keyring": {"service": "myservice"}}, '"username" key'),
    ],
)
def test_keyring_invalid(value: Any, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _getsecret(value)


def test_keyring_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "keyring", None)
    with pytest.raises(ImportError, match="keyring"):
        _getsecret({"keyring": "myuser"})
