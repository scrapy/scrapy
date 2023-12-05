# THIS MODULE IS FOR BACKWARDS COMPATIBILITY ONLY!
from typing import Iterable

from sybil import Region, Document
from sybil.parsers.rest import CaptureParser


def parse_captures(document: Document) -> Iterable[Region]:
    """
    A parser function to be included when your documentation makes use of
    :ref:`capture-parser` examples.
    """
    return CaptureParser()(document)
