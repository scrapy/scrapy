from __future__ import annotations

import json
import os
from typing import Any

from scrapy.utils.misc import load_object

_SOURCES = {"env", "keyring", "raw"}


def _resolve_secret(value: Any) -> str:
    """Return the secret that *value* holds or references.

    See :ref:`secret-settings` for the supported references.
    """
    if isinstance(value, dict):
        spec = value
    elif isinstance(value, str):
        try:
            spec = json.loads(value)
        except ValueError:
            return value
        # Any other JSON value, e.g. a service-account blob, is a literal
        # secret.
        if not isinstance(spec, dict) or not _SOURCES & spec.keys():
            return value
    else:
        return str(value)

    if "raw" in spec:
        raw = spec["raw"]
        return raw if isinstance(raw, str) else json.dumps(raw)
    if "env" in spec:
        try:
            return os.environ[spec["env"]]
        except KeyError:
            raise KeyError(f"Environment variable {spec['env']!r} is not set") from None
    if "keyring" in spec:
        return _resolve_keyring(spec["keyring"])
    raise ValueError(
        f"Secret references need one of these keys: {', '.join(sorted(_SOURCES))}"
    )


def _resolve_keyring(kr: Any) -> str:
    try:
        import keyring  # noqa: PLC0415
    except ImportError:
        raise ImportError(
            "Install the 'keyring' package to use keyring-based secrets: "
            "pip install keyring"
        ) from None

    if isinstance(kr, str):
        username: str = kr
        service: str = "scrapy"
        backend_path: str | None = None
    elif isinstance(kr, dict):
        if "username" not in kr:
            raise ValueError('"keyring" object must have a "username" key')
        username = kr["username"]
        service = kr.get("service", "scrapy")
        backend_path = kr.get("backend")
    else:
        raise ValueError('"keyring" must be a string or an object')

    if backend_path is not None:
        backend_cls = load_object(backend_path)
        value: str | None = backend_cls().get_password(service, username)
    else:
        value = keyring.get_password(service, username)

    if value is None:
        raise KeyError(
            f"No keyring entry found for service={service!r}, username={username!r}"
        )
    return value
