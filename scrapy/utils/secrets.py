from __future__ import annotations

import json
import os
import warnings
from logging import getLogger
from pathlib import Path
from typing import Any

from scrapy.utils.misc import load_object

logger = getLogger(__name__)


def resolve_secret(value: Any, default: str | None = None) -> str | None:
    """Resolve a raw value as a secret string.

    Plain strings and non-JSON values are returned as-is. JSON object values
    that contain a recognised source key are resolved against that source:

    -   ``{"env": "VAR"}`` — read from the *VAR* environment variable. If the
        variable is not set a warning is logged and *default* is returned.

    -   ``{"keyring": "username"}`` or ``{"keyring": {"username": "…",
        "service": "…", "backend": "…"}}`` — read from the system keyring
        (requires the keyring_ package; default service is ``"scrapy"``). If
        the entry does not exist a :exc:`KeyError` is raised.

        .. _keyring: https://pypi.org/project/keyring/

    -   ``{"raw": <value>}`` — return the inner value directly (JSON-serialised
        if it is not a string). Use this as an escape hatch for literal JSON
        secrets whose keys would otherwise be misinterpreted as a source
        reference.

    Any other JSON value or object is returned as the original raw string,
    preserving backward compatibility.

    See :ref:`secret-settings` for full usage examples.

    :param value: the raw setting value to resolve.
    :param default: value to return when an ``"env"`` reference cannot be
        resolved because the environment variable is not set. Defaults to
        ``None``.
    """
    if isinstance(value, dict):
        spec: dict[str, Any] = value
        raw: str | None = None
    elif isinstance(value, str):
        raw = value
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return value
        if not isinstance(parsed, dict):
            # JSON but not an object (string, number, bool, list) — treat as
            # a plain string secret.
            return value
        spec = parsed
    else:
        return str(value)

    if "raw" in spec:
        inner = spec["raw"]
        return inner if isinstance(inner, str) else json.dumps(inner)

    if "env" in spec:
        return _resolve_env(spec, default)

    if "keyring" in spec:
        return _resolve_keyring(spec)

    # JSON object with no recognised source key — it is a literal secret (e.g.
    # a JSON blob stored directly in settings).
    return raw


def _resolve_env(spec: dict[str, Any], default: str | None) -> str | None:
    var = spec["env"]
    if not isinstance(var, str):
        raise ValueError(f'"env" must be a string, got {type(var).__name__!r}')
    value = os.environ.get(var)
    if value is None:
        logger.warning(
            f"Environment variable {var!r} referenced in a secret reference "
            "value is not set; treating as undefined."
        )
        return default
    return value


def _resolve_keyring(spec: dict[str, Any]) -> str:
    try:
        import keyring  # noqa: PLC0415
    except ImportError:
        raise ImportError(
            "Install the 'keyring' package to use keyring-based secrets: "
            "pip install keyring"
        ) from None

    kr = spec["keyring"]
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


def _load_dotenv(path: str = ".env", override: bool = False) -> None:
    """Load environment variables from a :file:`.env` file into :data:`os.environ`.

    The file is resolved relative to the current working directory. If it
    does not exist the call is a no-op. Requires the ``python-dotenv``
    package; if the package is not installed a :exc:`UserWarning` is emitted
    and the call returns without raising.

    :param path: path to the :file:`.env` file. Defaults to ``".env"``.
    :param override: when ``True``, values from the file override existing
        environment variables. Defaults to ``False`` so that real environment
        variables always take precedence over the file.
    """
    if not Path(path).is_file():
        return
    try:
        from dotenv import load_dotenv as _load  # noqa: PLC0415
    except ImportError:
        warnings.warn(
            "Install the 'python-dotenv' package to load a .env file: "
            "pip install python-dotenv",
            UserWarning,
            stacklevel=2,
        )
        return
    _load(dotenv_path=path, override=override)
