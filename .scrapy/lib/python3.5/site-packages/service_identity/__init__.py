"""
Verify service identities.
"""

from __future__ import absolute_import, division, print_function

from . import pyopenssl
from .exceptions import (
    CertificateError,
    SubjectAltNameWarning,
    VerificationError,
)


__version__ = "16.0.0"

__title__ = "service_identity"
__description__ = "Service identity verification for pyOpenSSL."
__uri__ = "https://service-identity.readthedocs.org/"

__author__ = "Hynek Schlawack"
__email__ = "hs@ox.cx"

__license__ = "MIT"
__copyright__ = "Copyright (c) 2014 Hynek Schlawack"


__all__ = [
    "CertificateError",
    "SubjectAltNameWarning",
    "VerificationError",
    "pyopenssl",
]
