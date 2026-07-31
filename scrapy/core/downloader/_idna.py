"""Workarounds for the idna package rejecting IDNA-2003-only hostnames.

Some registered domains, such as emoji domains, are only valid under IDNA
2003, so the idna package (used by Twisted) rejects them, even in their
punycode (``xn--``) form, while the IDNA 2003 implementation of the standard
library handles them fine (https://github.com/scrapy/scrapy/issues/4330).

The ideal long-term fix would be for Twisted's ``_idnaBytes()`` to fall back
to the standard library codec when ``idna.encode()`` raises; until then,
:func:`_install_twisted_idna_fallbacks` patches such a fallback into the
Twisted modules that use ``_idnaBytes()``/``_idnaText()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from twisted.internet import _idna as _twisted_idna

if TYPE_CHECKING:
    from collections.abc import Callable

_original_idna_bytes: Callable[[str], bytes] | None = getattr(
    _twisted_idna, "_idnaBytes", None
)
_original_idna_text: Callable[[bytes], str] | None = getattr(
    _twisted_idna, "_idnaText", None
)


def _safe_hostname_bytes(hostname: str) -> bytes:
    """Punycode *hostname* without IDNA-2008 validation.

    Raise UnicodeError if it cannot be represented at all.
    """
    try:
        # The standard library codec implements IDNA 2003, which accepts
        # emoji labels and passes through already-encoded (xn--) ones.
        return hostname.encode("idna")
    except UnicodeError:
        # e.g. ASCII labels that the standard library rejects, such as
        # overlong ones; re-raises UnicodeError for non-ASCII hostnames.
        return hostname.encode("ascii")


def _patched_idna_bytes(text: str) -> bytes:
    assert _original_idna_bytes is not None
    try:
        return _original_idna_bytes(text)
    except UnicodeError:  # parent class of idna.IDNAError
        return _safe_hostname_bytes(text)


def _patched_idna_text(octets: bytes) -> str:
    assert _original_idna_text is not None
    try:
        return _original_idna_text(octets)
    except UnicodeError:
        return octets.decode("idna")


def _install_twisted_idna_fallbacks() -> None:
    """Patch ``_idnaBytes()``/``_idnaText()`` in the Twisted modules that use
    them for client connections.

    Those modules bind the functions at import time (``from ._idna import
    _idnaBytes``), so each module reference needs patching, not just
    ``twisted.internet._idna``. Names not found (e.g. after a Twisted
    refactoring) or already replaced are skipped, keeping the default
    behavior.
    """
    from twisted.internet import _resolver, _sslverify, endpoints  # noqa: PLC0415

    for module in (_twisted_idna, _resolver, _sslverify, endpoints):
        if (
            _original_idna_bytes is not None
            and getattr(module, "_idnaBytes", None) is _original_idna_bytes
        ):
            module._idnaBytes = _patched_idna_bytes  # type: ignore[attr-defined]
        if (
            _original_idna_text is not None
            and getattr(module, "_idnaText", None) is _original_idna_text
        ):
            module._idnaText = _patched_idna_text  # type: ignore[attr-defined]
