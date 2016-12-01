# -*- test-case-name: twisted.web.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Interface definitions for L{twisted.web}.

@var UNKNOWN_LENGTH: An opaque object which may be used as the value of
    L{IBodyProducer.length} to indicate that the length of the entity
    body is not known in advance.
"""

from twisted.web.iweb import (
    IRequest, ICredentialFactory, IBodyProducer, IRenderable, ITemplateLoader,
    IResponse, _IRequestEncoder, _IRequestEncoderFactory, UNKNOWN_LENGTH,
)

__all__ = [
    "ICredentialFactory", "IRequest",
    "IBodyProducer", "IRenderable", "IResponse", "_IRequestEncoder",
    "_IRequestEncoderFactory",

    "UNKNOWN_LENGTH"]
