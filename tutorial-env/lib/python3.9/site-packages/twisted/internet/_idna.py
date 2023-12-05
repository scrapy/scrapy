# -*- test-case-name: twisted.test.test_sslverify -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Shared interface to IDNA encoding and decoding, using the C{idna} PyPI package
if available, otherwise the stdlib implementation.
"""


def _idnaBytes(text: str) -> bytes:
    """
    Convert some text typed by a human into some ASCII bytes.

    This is provided to allow us to use the U{partially-broken IDNA
    implementation in the standard library <http://bugs.python.org/issue17305>}
    if the more-correct U{idna <https://pypi.python.org/pypi/idna>} package is
    not available; C{service_identity} is somewhat stricter about this.

    @param text: A domain name, hopefully.
    @type text: L{unicode}

    @return: The domain name's IDNA representation, encoded as bytes.
    @rtype: L{bytes}
    """
    try:
        import idna
    except ImportError:
        return text.encode("idna")
    else:
        return idna.encode(text)


def _idnaText(octets: bytes) -> str:
    """
    Convert some IDNA-encoded octets into some human-readable text.

    Currently only used by the tests.

    @param octets: Some bytes representing a hostname.
    @type octets: L{bytes}

    @return: A human-readable domain name.
    @rtype: L{unicode}
    """
    try:
        import idna
    except ImportError:
        return octets.decode("idna")
    else:
        return idna.decode(octets)
