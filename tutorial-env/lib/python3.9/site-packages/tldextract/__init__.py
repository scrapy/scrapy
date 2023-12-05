"""Export tldextract's public interface."""

from . import _version
from .tldextract import TLDExtract, extract

__version__: str = _version.version

__all__ = [
    "extract",
    "TLDExtract",
    "__version__",
]
