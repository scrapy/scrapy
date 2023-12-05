# -*- test-case-name: twisted.web.test.test_template -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
HTML rendering for twisted.web.

@var VALID_HTML_TAG_NAMES: A list of recognized HTML tag names, used by the
    L{tag} object.

@var TEMPLATE_NAMESPACE: The XML namespace used to identify attributes and
    elements used by the templating system, which should be removed from the
    final output document.

@var tags: A convenience object which can produce L{Tag} objects on demand via
    attribute access.  For example: C{tags.div} is equivalent to C{Tag("div")}.
    Tags not specified in L{VALID_HTML_TAG_NAMES} will result in an
    L{AttributeError}.
"""


__all__ = [
    "TEMPLATE_NAMESPACE",
    "VALID_HTML_TAG_NAMES",
    "Element",
    "Flattenable",
    "TagLoader",
    "XMLString",
    "XMLFile",
    "renderer",
    "flatten",
    "flattenString",
    "tags",
    "Comment",
    "CDATA",
    "Tag",
    "slot",
    "CharRef",
    "renderElement",
]

from ._stan import CharRef
from ._template_util import (
    CDATA,
    TEMPLATE_NAMESPACE,
    VALID_HTML_TAG_NAMES,
    Comment,
    Element,
    Flattenable,
    Tag,
    TagLoader,
    XMLFile,
    XMLString,
    flatten,
    flattenString,
    renderElement,
    renderer,
    slot,
    tags,
)
