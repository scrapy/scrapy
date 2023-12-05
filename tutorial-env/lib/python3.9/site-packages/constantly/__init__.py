# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from constantly._constants import (
    NamedConstant, Names, ValueConstant, Values, FlagConstant, Flags
)

from . import _version
__version__ = _version.get_versions()['version']

__author__  = "Twisted Matrix Laboratories"
__license__ = "MIT"
__copyright__ = "Copyright 2011-2015 {0}".format(__author__)


__all__ = [
    'NamedConstant',
    'ValueConstant',
    'FlagConstant',
    'Names',
    'Values',
    'Flags',
]
