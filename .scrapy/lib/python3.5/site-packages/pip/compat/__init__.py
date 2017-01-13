"""Stuff that differs in different Python versions and platform
distributions."""
from __future__ import absolute_import, division

import os
import sys

from pip._vendor.six import text_type

try:
    from logging.config import dictConfig as logging_dictConfig
except ImportError:
    from pip.compat.dictconfig import dictConfig as logging_dictConfig

try:
    import ipaddress
except ImportError:
    try:
        from pip._vendor import ipaddress
    except ImportError:
        import ipaddr as ipaddress
        ipaddress.ip_address = ipaddress.IPAddress
        ipaddress.ip_network = ipaddress.IPNetwork


__all__ = [
    "logging_dictConfig", "ipaddress", "uses_pycache", "console_to_str",
    "native_str", "get_path_uid", "stdlib_pkgs", "WINDOWS",
]


if sys.version_info >= (3, 4):
    uses_pycache = True
    from importlib.util import cache_from_source
else:
    import imp
    uses_pycache = hasattr(imp, 'cache_from_source')
    if uses_pycache:
        cache_from_source = imp.cache_from_source
    else:
        cache_from_source = None


if sys.version_info >= (3,):
    def console_to_str(s):
        try:
            return s.decode(sys.__stdout__.encoding)
        except UnicodeDecodeError:
            return s.decode('utf_8')

    def native_str(s, replace=False):
        if isinstance(s, bytes):
            return s.decode('utf-8', 'replace' if replace else 'strict')
        return s

else:
    def console_to_str(s):
        return s

    def native_str(s, replace=False):
        # Replace is ignored -- unicode to UTF-8 can't fail
        if isinstance(s, text_type):
            return s.encode('utf-8')
        return s


def total_seconds(td):
    if hasattr(td, "total_seconds"):
        return td.total_seconds()
    else:
        val = td.microseconds + (td.seconds + td.days * 24 * 3600) * 10 ** 6
        return val / 10 ** 6


def get_path_uid(path):
    """
    Return path's uid.

    Does not follow symlinks:
        https://github.com/pypa/pip/pull/935#discussion_r5307003

    Placed this function in compat due to differences on AIX and
    Jython, that should eventually go away.

    :raises OSError: When path is a symlink or can't be read.
    """
    if hasattr(os, 'O_NOFOLLOW'):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        file_uid = os.fstat(fd).st_uid
        os.close(fd)
    else:  # AIX and Jython
        # WARNING: time of check vulnerabity, but best we can do w/o NOFOLLOW
        if not os.path.islink(path):
            # older versions of Jython don't have `os.fstat`
            file_uid = os.stat(path).st_uid
        else:
            # raise OSError for parity with os.O_NOFOLLOW above
            raise OSError(
                "%s is a symlink; Will not return uid for symlinks" % path
            )
    return file_uid


# packages in the stdlib that may have installation metadata, but should not be
# considered 'installed'.  this theoretically could be determined based on
# dist.location (py27:`sysconfig.get_paths()['stdlib']`,
# py26:sysconfig.get_config_vars('LIBDEST')), but fear platform variation may
# make this ineffective, so hard-coding
stdlib_pkgs = ['python', 'wsgiref']
if sys.version_info >= (2, 7):
    stdlib_pkgs.extend(['argparse'])


# windows detection, covers cpython and ironpython
WINDOWS = (sys.platform.startswith("win") or
           (sys.platform == 'cli' and os.name == 'nt'))
