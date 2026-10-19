from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy.http.response import Response

if TYPE_CHECKING:
    import os


class BodyFileResponse(Response):
    """A :class:`~scrapy.http.Response` whose body was written to a file, as
    requested with the :reqmeta:`body_file` request meta key.

    .. versionadded:: VERSION

    Reading :attr:`~scrapy.http.Response.body` raises :exc:`AttributeError`.
    """

    attributes: tuple[str, ...] = (
        *(attr for attr in Response.attributes if attr != "body"),
        "body_file",
    )

    __slots__ = ("body_file",)

    def __init__(self, *args: Any, body_file: str | os.PathLike[str], **kwargs: Any):
        if "body" in kwargs:
            raise TypeError(f"{type(self).__name__} does not take a body.")
        super().__init__(*args, **kwargs)
        self.body_file: str | os.PathLike[str] = body_file
        """Path of the file that holds the response body."""

    @property
    def body(self) -> bytes:
        raise AttributeError(
            f"The body of {self} is not in memory, it was written to "
            f"{self.body_file!r}, as requested with the body_file request meta "
            f"key."
        )
