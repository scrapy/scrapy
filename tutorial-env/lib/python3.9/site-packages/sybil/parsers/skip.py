# THIS MODULE IS FOR BACKWARDS COMPATIBILITY ONLY!
from typing import Iterable

from sybil import Region, Document
from .rest import SkipParser


def skip(document: Document) -> Iterable[Region]:
    """
    A parser function to be included when your documentation makes use of
    :ref:`skipping <skip-parser>` examples in a document.
    """
    return SkipParser()(document)
