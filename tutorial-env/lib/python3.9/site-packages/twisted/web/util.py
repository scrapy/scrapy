# -*- test-case-name: twisted.web.test.test_util -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
An assortment of web server-related utilities.
"""

__all__ = [
    "redirectTo",
    "Redirect",
    "ChildRedirector",
    "ParentRedirect",
    "DeferredResource",
    "FailureElement",
    "formatFailure",
    # publicized by unit tests:
    "_FrameElement",
    "_SourceFragmentElement",
    "_SourceLineElement",
    "_StackElement",
    "_PRE",
]

from ._template_util import (
    _PRE,
    ChildRedirector,
    DeferredResource,
    FailureElement,
    ParentRedirect,
    Redirect,
    _FrameElement,
    _SourceFragmentElement,
    _SourceLineElement,
    _StackElement,
    formatFailure,
    redirectTo,
)
