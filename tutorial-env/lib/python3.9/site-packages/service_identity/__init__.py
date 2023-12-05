"""
Verify service identities.
"""


from . import cryptography, hazmat, pyopenssl
from .exceptions import (
    CertificateError,
    SubjectAltNameWarning,
    VerificationError,
)


__title__ = "service-identity"

__author__ = "Hynek Schlawack"

__license__ = "MIT"
__copyright__ = "Copyright (c) 2014 " + __author__


__all__ = [
    "CertificateError",
    "SubjectAltNameWarning",
    "VerificationError",
    "hazmat",
    "cryptography",
    "pyopenssl",
]


def __getattr__(name: str) -> str:
    dunder_to_metadata = {
        "__version__": "version",
        "__description__": "summary",
        "__uri__": "",
        "__url__": "",
        "__email__": "",
    }
    if name not in dunder_to_metadata.keys():
        raise AttributeError(f"module {__name__} has no attribute {name}")

    import warnings

    from importlib.metadata import metadata

    warnings.warn(
        f"Accessing service_identity.{name} is deprecated and will be "
        "removed in a future release. Use importlib.metadata directly "
        "to query packaging metadata.",
        DeprecationWarning,
        stacklevel=2,
    )

    meta = metadata("service-identity")

    if name in ("__uri__", "__url__"):
        return meta["Project-URL"].split(" ", 1)[-1]

    if name == "__email__":
        return meta["Author-email"].split("<", 1)[1].rstrip(">")

    return meta[dunder_to_metadata[name]]
