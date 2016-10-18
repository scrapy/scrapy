from __future__ import absolute_import, division, print_function

from ._funcs import (
    asdict,
    assoc,
    astuple,
    has,
)
from ._make import (
    Attribute,
    Factory,
    NOTHING,
    attr,
    attributes,
    fields,
    make_class,
    validate,
)
from ._config import (
    get_run_validators,
    set_run_validators,
)
from . import exceptions
from . import filters
from . import validators


__version__ = "16.2.0"

__title__ = "attrs"
__description__ = "Attributes Without Boilerplate"
__uri__ = "https://attrs.readthedocs.io/"
__doc__ = __description__ + " <" + __uri__ + ">"

__author__ = "Hynek Schlawack"
__email__ = "hs@ox.cx"

__license__ = "MIT"
__copyright__ = "Copyright (c) 2015 Hynek Schlawack"


s = attrs = attributes
ib = attrib = attr

__all__ = [
    "Attribute",
    "Factory",
    "NOTHING",
    "asdict",
    "astuple",
    "assoc",
    "attr",
    "attrib",
    "attributes",
    "attrs",
    "exceptions",
    "fields",
    "filters",
    "get_run_validators",
    "has",
    "ib",
    "make_class",
    "s",
    "set_run_validators",
    "validate",
    "validators",
]
