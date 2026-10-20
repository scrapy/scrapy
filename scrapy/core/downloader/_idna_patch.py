"""Fallbacks for hostnames that the ``idna`` package rejects but that resolve fine.

Twisted encodes hostnames with ``idna``, which enforces IDNA 2008 and rejects
emoji domains even in punycode (``xn--``) form
(https://github.com/scrapy/scrapy/issues/4330) and domains with underscores
(https://github.com/scrapy/scrapy/issues/3321). The standard library codec
implements IDNA 2003 and handles both, so :func:`_install_twisted_idna_fallbacks`
patches Twisted to fall back to it. Ideally Twisted would do this itself.
"""

from __future__ import annotations

import re

from twisted.internet import _idna

_original_idna_bytes = _idna._idnaBytes
_original_idna_text = _idna._idnaText

# Letters, digits and hyphens, plus the underscore that the idna package
# rejects. The stdlib codec passes any other ASCII through as well, e.g. the
# ":" that Twisted parses out of a bracketless IPv6 netloc, and Twisted must
# keep treating those as invalid hostnames instead of resolving them.
_HOSTNAME = re.compile(rb"[a-zA-Z0-9._\-]+\Z")


def _safe_hostname_bytes(hostname: str) -> bytes:
    """Punycode *hostname* with IDNA 2003, which accepts emoji labels and passes
    already-encoded (``xn--``) ones through.

    Raises UnicodeError if it cannot be encoded into a hostname at all.
    """
    try:
        encoded = hostname.encode("idna")
    except UnicodeError:
        # The stdlib codec also rejects some ASCII hostnames, e.g. overlong
        # labels; non-ASCII ones raise UnicodeError again here.
        encoded = hostname.encode("ascii")
    if not _HOSTNAME.match(encoded):
        raise UnicodeError(f"invalid hostname: {hostname}")
    return encoded


def _patched_idna_bytes(text: str) -> bytes:
    try:
        return _original_idna_bytes(text)
    except UnicodeError:  # parent class of idna.IDNAError
        return _safe_hostname_bytes(text)


def _patched_idna_text(octets: bytes) -> str:
    try:
        return _original_idna_text(octets)
    except UnicodeError:
        if not _HOSTNAME.match(octets):
            raise
        return octets.decode("idna")


def _install_twisted_idna_fallbacks() -> None:
    """Patch ``_idnaBytes()``/``_idnaText()`` wherever Twisted uses them for
    client connections.

    Each module binds them at import time, so every reference needs patching,
    not just ``twisted.internet._idna``. Names that are missing or already
    patched are left alone.
    """
    from twisted.internet import _resolver, _sslverify, endpoints  # noqa: PLC0415

    patches = (
        ("_idnaBytes", _original_idna_bytes, _patched_idna_bytes),
        ("_idnaText", _original_idna_text, _patched_idna_text),
    )
    for module in (_idna, _resolver, _sslverify, endpoints):
        for name, original, patched in patches:
            if getattr(module, name, None) is original:
                setattr(module, name, patched)
