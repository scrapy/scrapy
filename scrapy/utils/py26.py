"""
This module provides functions added in Python 2.6, which weren't yet available
in Python 2.5. The Python 2.6 function is used when available.
"""

import sys
import os
import fnmatch
import pkgutil
from shutil import copy2, copystat

__all__ = ['cpu_count', 'copytree', 'ignore_patterns']

try:
    import multiprocessing
    cpu_count = multiprocessing.cpu_count
except ImportError:
    def cpu_count():
        '''
        Returns the number of CPUs in the system
        '''
        if sys.platform == 'win32':
            try:
                num = int(os.environ['NUMBER_OF_PROCESSORS'])
            except (ValueError, KeyError):
                num = 0
        elif 'bsd' in sys.platform or sys.platform == 'darwin':
            try:
                num = int(os.popen('sysctl -n hw.ncpu').read())
            except ValueError:
                num = 0
        else:
            try:
                num = os.sysconf('SC_NPROCESSORS_ONLN')
            except (ValueError, OSError, AttributeError):
                num = 0

        if num >= 1:
            return num
        else:
            raise NotImplementedError('cannot determine number of cpus')

if sys.version_info >= (2, 6):
    from shutil import copytree, ignore_patterns
else:
    try:
        WindowsError
    except NameError:
        WindowsError = None

    class Error(EnvironmentError):
        pass

    def ignore_patterns(*patterns):
        def _ignore_patterns(path, names):
            ignored_names = []
            for pattern in patterns:
                ignored_names.extend(fnmatch.filter(names, pattern))
            return set(ignored_names)
        return _ignore_patterns

    def copytree(src, dst, symlinks=False, ignore=None):
        names = os.listdir(src)
        if ignore is not None:
            ignored_names = ignore(src, names)
        else:
            ignored_names = set()

        os.makedirs(dst)
        errors = []
        for name in names:
            if name in ignored_names:
                continue
            srcname = os.path.join(src, name)
            dstname = os.path.join(dst, name)
            try:
                if symlinks and os.path.islink(srcname):
                    linkto = os.readlink(srcname)
                    os.symlink(linkto, dstname)
                elif os.path.isdir(srcname):
                    copytree(srcname, dstname, symlinks, ignore)
                else:
                    copy2(srcname, dstname)
                # XXX What about devices, sockets etc.?
            except (IOError, os.error), why:
                errors.append((srcname, dstname, str(why)))
            # catch the Error from the recursive copytree so that we can
            # continue with other files
            except Error, err:
                errors.extend(err.args[0])
        try:
            copystat(src, dst)
        except OSError, why:
            if WindowsError is not None and isinstance(why, WindowsError):
                # Copying file access times may fail on Windows
                pass
            else:
                errors.extend((src, dst, str(why)))
        if errors:
            raise Error, errors

try:
    import json
except ImportError:
    import simplejson as json


def _get_data(package, resource):
    loader = pkgutil.get_loader(package)
    if loader is None or not hasattr(loader, 'get_data'):
        return None
    mod = sys.modules.get(package) or loader.load_module(package)
    if mod is None or not hasattr(mod, '__file__'):
        return None

    # Modify the resource name to be compatible with the loader.get_data
    # signature - an os.path format "filename" starting with the dirname of
    # the package's __file__
    parts = resource.split('/')
    parts.insert(0, os.path.dirname(mod.__file__))
    resource_name = os.path.join(*parts)
    return loader.get_data(resource_name)

# pkgutil.get_data() not available in python 2.5
# see http://docs.python.org/release/2.5/lib/module-pkgutil.html
try:
    get_data = pkgutil.get_data
except AttributeError:
    get_data = _get_data
