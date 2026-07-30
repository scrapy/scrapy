# This module deliberately does not use "from __future__ import annotations",
# so that on Python 3.14+ its annotations are lazily evaluated as per PEP 649
# instead of being turned into strings as per PEP 563. As it also annotates
# objects that are only imported under TYPE_CHECKING, importing it on older
# Python versions raises NameError, so conftest.py excludes it from collection
# there and the tests that use it are skipped.
# pylint: disable=used-before-assignment
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # TC004 is exactly what this module needs to reproduce: an import that is
    # only available to type checkers but is referenced from an annotation that
    # is evaluated (lazily) at run time.
    import scrapy  # noqa: TC004


class MiddlewareWithLazyAnnotations:
    """A middleware whose method annotations cannot be resolved at run time."""

    def process_exception(
        self, request: scrapy.Request, exception: Exception, spider=None
    ) -> None:
        pass


def func_with_lazy_annotations(request: scrapy.Request, spider: scrapy.Spider) -> None:
    pass
