# -*- coding: utf-8 -*-
"""
    sphinx.util.osutil
    ~~~~~~~~~~~~~~~~~~

    Operating system-related utility functions for Sphinx.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""
from __future__ import print_function

import os
import re
import sys
import time
import errno
import locale
import shutil
from os import path
import contextlib

from six import PY2, text_type

# Errnos that we need.
EEXIST = getattr(errno, 'EEXIST', 0)
ENOENT = getattr(errno, 'ENOENT', 0)
EPIPE  = getattr(errno, 'EPIPE', 0)
EINVAL = getattr(errno, 'EINVAL', 0)

# SEP separates path elements in the canonical file names
#
# Define SEP as a manifest constant, not so much because we expect it to change
# in the future as to avoid the suspicion that a stray "/" in the code is a
# hangover from more *nix-oriented origins.
SEP = "/"


def os_path(canonicalpath):
    return canonicalpath.replace(SEP, path.sep)


def canon_path(nativepath):
    """Return path in OS-independent form"""
    return nativepath.replace(path.sep, SEP)


def relative_uri(base, to):
    """Return a relative URL from ``base`` to ``to``."""
    if to.startswith(SEP):
        return to
    b2 = base.split(SEP)
    t2 = to.split(SEP)
    # remove common segments (except the last segment)
    for x, y in zip(b2[:-1], t2[:-1]):
        if x != y:
            break
        b2.pop(0)
        t2.pop(0)
    if b2 == t2:
        # Special case: relative_uri('f/index.html','f/index.html')
        # returns '', not 'index.html'
        return ''
    if len(b2) == 1 and t2 == ['']:
        # Special case: relative_uri('f/index.html','f/') should
        # return './', not ''
        return '.' + SEP
    return ('..' + SEP) * (len(b2)-1) + SEP.join(t2)


def ensuredir(path):
    """Ensure that a path exists."""
    try:
        os.makedirs(path)
    except OSError as err:
        # 0 for Jython/Win32
        if err.errno not in [0, EEXIST]:
            raise


# This function is same as os.walk of Python2.6, 2.7, 3.2, 3.3 except a
# customization that check UnicodeError.
# The customization obstacle to replace the function with the os.walk.
def walk(top, topdown=True, followlinks=False):
    """Backport of os.walk from 2.6, where the *followlinks* argument was
    added.
    """
    names = os.listdir(top)

    dirs, nondirs = [], []
    for name in names:
        try:
            fullpath = path.join(top, name)
        except UnicodeError:
            print('%s:: ERROR: non-ASCII filename not supported on this '
                  'filesystem encoding %r, skipped.' % (name, fs_encoding),
                  file=sys.stderr)
            continue
        if path.isdir(fullpath):
            dirs.append(name)
        else:
            nondirs.append(name)

    if topdown:
        yield top, dirs, nondirs
    for name in dirs:
        fullpath = path.join(top, name)
        if followlinks or not path.islink(fullpath):
            for x in walk(fullpath, topdown, followlinks):
                yield x
    if not topdown:
        yield top, dirs, nondirs


def mtimes_of_files(dirnames, suffix):
    for dirname in dirnames:
        for root, dirs, files in os.walk(dirname):
            for sfile in files:
                if sfile.endswith(suffix):
                    try:
                        yield path.getmtime(path.join(root, sfile))
                    except EnvironmentError:
                        pass


def movefile(source, dest):
    """Move a file, removing the destination if it exists."""
    if os.path.exists(dest):
        try:
            os.unlink(dest)
        except OSError:
            pass
    os.rename(source, dest)


def copytimes(source, dest):
    """Copy a file's modification times."""
    st = os.stat(source)
    if hasattr(os, 'utime'):
        os.utime(dest, (st.st_atime, st.st_mtime))


def copyfile(source, dest):
    """Copy a file and its modification times, if possible."""
    shutil.copyfile(source, dest)
    try:
        # don't do full copystat because the source may be read-only
        copytimes(source, dest)
    except OSError:
        pass


no_fn_re = re.compile(r'[^a-zA-Z0-9_-]')


def make_filename(string):
    return no_fn_re.sub('', string) or 'sphinx'


def ustrftime(format, *args):
    # [DEPRECATED] strftime for unicode strings
    # It will be removed at Sphinx-1.5
    if not args:
        # If time is not specified, try to use $SOURCE_DATE_EPOCH variable
        # See https://wiki.debian.org/ReproducibleBuilds/TimestampsProposal
        source_date_epoch = os.getenv('SOURCE_DATE_EPOCH')
        if source_date_epoch is not None:
            time_struct = time.gmtime(float(source_date_epoch))
            args = [time_struct]
    if PY2:
        # if a locale is set, the time strings are encoded in the encoding
        # given by LC_TIME; if that is available, use it
        enc = locale.getlocale(locale.LC_TIME)[1] or 'utf-8'
        return time.strftime(text_type(format).encode(enc), *args).decode(enc)
    else:  # Py3
        # On Windows, time.strftime() and Unicode characters will raise UnicodeEncodeError.
        # http://bugs.python.org/issue8304
        try:
            return time.strftime(format, *args)
        except UnicodeEncodeError:
            r = time.strftime(format.encode('unicode-escape').decode(), *args)
            return r.encode().decode('unicode-escape')


def safe_relpath(path, start=None):
    try:
        return os.path.relpath(path, start)
    except ValueError:
        return path


fs_encoding = sys.getfilesystemencoding() or sys.getdefaultencoding()


def abspath(pathdir):
    pathdir = path.abspath(pathdir)
    if isinstance(pathdir, bytes):
        pathdir = pathdir.decode(fs_encoding)
    return pathdir


def getcwd():
    if hasattr(os, 'getcwdu'):
        return os.getcwdu()
    return os.getcwd()


@contextlib.contextmanager
def cd(target_dir):
    cwd = getcwd()
    try:
        os.chdir(target_dir)
        yield
    finally:
        os.chdir(cwd)


def rmtree(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
