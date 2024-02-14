"""
This module defines the Link object used in Link extractors.

For actual link extractors implementation see scrapy.linkextractors, or
its documentation in: docs/topics/link-extractors.rst
"""
from typing import Any


class Link:
    """Link objects represent an extracted link by the LinkExtractor.

    Using the anchor tag sample below to illustrate the parameters::

            <a href="https://example.com/nofollow.html#foo" rel="nofollow">Dont follow this one</a>

    :param url: the absolute url being linked to in the anchor tag.
                From the sample, this is ``https://example.com/nofollow.html``.

    :param text: the text in the anchor tag. From the sample, this is ``Dont follow this one``.

    :param fragment: the part of the url after the hash symbol. From the sample, this is ``foo``.

    :param nofollow: an indication of the presence or absence of a nofollow value in the ``rel`` attribute
                    of the anchor tag.
    """

    __slots__ = ["url", "text", "fragment", "nofollow"]

    def __init__(
        self, url: str, text: str = "", fragment: str = "", nofollow: bool = False
    ):
        if not isinstance(url, str):
            got = url.__class__.__name__
            raise TypeError(f"Link urls must be str objects, got {got}")
        self.url: str = url
        self.text: str = text
        self.fragment: str = fragment
        self.nofollow: bool = nofollow

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Link):
            raise NotImplementedError
        return (
            self.url == other.url
            and self.text == other.text
            and self.fragment == other.fragment
            and self.nofollow == other.nofollow
        )

    def __hash__(self) -> int:
        return (
            hash(self.url) ^ hash(self.text) ^ hash(self.fragment) ^ hash(self.nofollow)
        )

    def __repr__(self) -> str:
        return (
            f"Link(url={self.url!r}, text={self.text!r}, "
            f"fragment={self.fragment!r}, nofollow={self.nofollow!r})"
        )
