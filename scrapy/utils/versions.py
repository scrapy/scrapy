import platform
import sys

import cssselect
import lxml.etree
import parsel
import twisted
import w3lib

import scrapy


def scrapy_components_versions():
    lxml_version = ".".join(map(str, lxml.etree.LXML_VERSION))
    libxml2_version = ".".join(map(str, lxml.etree.LIBXML_VERSION))
    try:
        w3lib_version = w3lib.__version__
    except AttributeError:
        w3lib_version = "<1.14.3"
    try:
        import cryptography
        cryptography_version = cryptography.__version__
    except ImportError:
        cryptography_version = "unknown"

    return [
        ("Scrapy", scrapy.__version__),
        ("lxml", lxml_version),
        ("libxml2", libxml2_version),
        ("cssselect", cssselect.__version__),
        ("parsel", parsel.__version__),
        ("w3lib", w3lib_version),
        ("Twisted", twisted.version.short()),
        ("Python", sys.version.replace("\n", "- ")),
        ("pyOpenSSL", _get_openssl_version()),
        ("cryptography", cryptography_version),
        ("Platform",  platform.platform()),
    ]


def _get_openssl_version():
    try:
        import OpenSSL
        openssl = OpenSSL.SSL.SSLeay_version(OpenSSL.SSL.SSLEAY_VERSION)\
            .decode('ascii', errors='replace')
    # pyOpenSSL 0.12 does not expose openssl version
    except AttributeError:
        openssl = 'Unknown OpenSSL version'

    return '{} ({})'.format(OpenSSL.version.__version__, openssl)
