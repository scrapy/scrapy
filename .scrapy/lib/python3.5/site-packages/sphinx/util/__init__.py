# -*- coding: utf-8 -*-
"""
    sphinx.util
    ~~~~~~~~~~~

    Utility functions for Sphinx.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import os
import re
import sys
import fnmatch
import tempfile
import posixpath
import traceback
import unicodedata
from os import path
from codecs import open, BOM_UTF8
from collections import deque

from six import iteritems, text_type, binary_type
from six.moves import range
from six.moves.urllib.parse import urlsplit, urlunsplit, quote_plus, parse_qsl, urlencode
import docutils
from docutils.utils import relative_path

import jinja2

import sphinx
from sphinx.errors import PycodeError, SphinxParallelError, ExtensionError
from sphinx.util.console import strip_colors
from sphinx.util.osutil import fs_encoding

# import other utilities; partly for backwards compatibility, so don't
# prune unused ones indiscriminately
from sphinx.util.osutil import (  # noqa
    SEP, os_path, relative_uri, ensuredir, walk, mtimes_of_files, movefile,
    copyfile, copytimes, make_filename, ustrftime)
from sphinx.util.nodes import (   # noqa
    nested_parse_with_titles, split_explicit_title, explicit_title_re,
    caption_ref_re)
from sphinx.util.matching import patfilter  # noqa

# Generally useful regular expressions.
ws_re = re.compile(r'\s+')
url_re = re.compile(r'(?P<schema>.+)://.*')


# High-level utility functions.

def docname_join(basedocname, docname):
    return posixpath.normpath(
        posixpath.join('/' + basedocname, '..', docname))[1:]


def path_stabilize(filepath):
    "normalize path separater and unicode string"
    newpath = filepath.replace(os.path.sep, SEP)
    if isinstance(newpath, text_type):
        newpath = unicodedata.normalize('NFC', newpath)
    return newpath


def get_matching_files(dirname, exclude_matchers=()):
    """Get all file names in a directory, recursively.

    Exclude files and dirs matching some matcher in *exclude_matchers*.
    """
    # dirname is a normalized absolute path.
    dirname = path.normpath(path.abspath(dirname))
    dirlen = len(dirname) + 1    # exclude final os.path.sep

    for root, dirs, files in walk(dirname, followlinks=True):
        relativeroot = root[dirlen:]

        qdirs = enumerate(path_stabilize(path.join(relativeroot, dn))
                          for dn in dirs)
        qfiles = enumerate(path_stabilize(path.join(relativeroot, fn))
                           for fn in files)
        for matcher in exclude_matchers:
            qdirs = [entry for entry in qdirs if not matcher(entry[1])]
            qfiles = [entry for entry in qfiles if not matcher(entry[1])]

        dirs[:] = sorted(dirs[i] for (i, _) in qdirs)

        for i, filename in sorted(qfiles):
            yield filename


def get_matching_docs(dirname, suffixes, exclude_matchers=()):
    """Get all file names (without suffixes) matching a suffix in a directory,
    recursively.

    Exclude files and dirs matching a pattern in *exclude_patterns*.
    """
    suffixpatterns = ['*' + s for s in suffixes]
    for filename in get_matching_files(dirname, exclude_matchers):
        for suffixpattern in suffixpatterns:
            if fnmatch.fnmatch(filename, suffixpattern):
                yield filename[:-len(suffixpattern)+1]
                break


class FilenameUniqDict(dict):
    """
    A dictionary that automatically generates unique names for its keys,
    interpreted as filenames, and keeps track of a set of docnames they
    appear in.  Used for images and downloadable files in the environment.
    """
    def __init__(self):
        self._existing = set()

    def add_file(self, docname, newfile):
        if newfile in self:
            self[newfile][0].add(docname)
            return self[newfile][1]
        uniquename = path.basename(newfile)
        base, ext = path.splitext(uniquename)
        i = 0
        while uniquename in self._existing:
            i += 1
            uniquename = '%s%s%s' % (base, i, ext)
        self[newfile] = (set([docname]), uniquename)
        self._existing.add(uniquename)
        return uniquename

    def purge_doc(self, docname):
        for filename, (docs, unique) in list(self.items()):
            docs.discard(docname)
            if not docs:
                del self[filename]
                self._existing.discard(unique)

    def merge_other(self, docnames, other):
        for filename, (docs, unique) in other.items():
            for doc in docs & docnames:
                self.add_file(doc, filename)

    def __getstate__(self):
        return self._existing

    def __setstate__(self, state):
        self._existing = state


def copy_static_entry(source, targetdir, builder, context={},
                      exclude_matchers=(), level=0):
    """Copy a HTML builder static_path entry from source to targetdir.

    Handles all possible cases of files, directories and subdirectories.
    """
    if exclude_matchers:
        relpath = relative_path(path.join(builder.srcdir, 'dummy'), source)
        for matcher in exclude_matchers:
            if matcher(relpath):
                return
    if path.isfile(source):
        target = path.join(targetdir, path.basename(source))
        if source.lower().endswith('_t') and builder.templates:
            # templated!
            fsrc = open(source, 'r', encoding='utf-8')
            fdst = open(target[:-2], 'w', encoding='utf-8')
            fdst.write(builder.templates.render_string(fsrc.read(), context))
            fsrc.close()
            fdst.close()
        else:
            copyfile(source, target)
    elif path.isdir(source):
        if not path.isdir(targetdir):
            os.mkdir(targetdir)
        for entry in os.listdir(source):
            if entry.startswith('.'):
                continue
            newtarget = targetdir
            if path.isdir(path.join(source, entry)):
                newtarget = path.join(targetdir, entry)
            copy_static_entry(path.join(source, entry), newtarget,
                              builder, context, level=level+1,
                              exclude_matchers=exclude_matchers)


def copy_extra_entry(source, targetdir, exclude_matchers=()):
    """Copy a HTML builder extra_path entry from source to targetdir.

    Handles all possible cases of files, directories and subdirectories.
    """
    def excluded(path):
        relpath = relative_path(os.path.dirname(source), path)
        return any(matcher(relpath) for matcher in exclude_matchers)

    def copy_extra_file(source_, targetdir_):
        if not excluded(source_):
            target = path.join(targetdir_, os.path.basename(source_))
            copyfile(source_, target)

    if os.path.isfile(source):
        copy_extra_file(source, targetdir)
        return

    for root, dirs, files in os.walk(source):
        reltargetdir = os.path.join(targetdir, relative_path(source, root))
        for dir in dirs[:]:
            if excluded(os.path.join(root, dir)):
                dirs.remove(dir)
            else:
                target = os.path.join(reltargetdir, dir)
                if not path.exists(target):
                    os.mkdir(target)
        for file in files:
            copy_extra_file(os.path.join(root, file), reltargetdir)

_DEBUG_HEADER = '''\
# Sphinx version: %s
# Python version: %s (%s)
# Docutils version: %s %s
# Jinja2 version: %s
# Last messages:
%s
# Loaded extensions:
'''


def save_traceback(app):
    """Save the current exception's traceback in a temporary file."""
    import platform
    exc = sys.exc_info()[1]
    if isinstance(exc, SphinxParallelError):
        exc_format = '(Error in parallel process)\n' + exc.traceback
    else:
        exc_format = traceback.format_exc()
    fd, path = tempfile.mkstemp('.log', 'sphinx-err-')
    last_msgs = ''
    if app is not None:
        last_msgs = '\n'.join(
            '#   %s' % strip_colors(force_decode(s, 'utf-8')).strip()
            for s in app.messagelog)
    os.write(fd, (_DEBUG_HEADER %
                  (sphinx.__display_version__,
                   platform.python_version(),
                   platform.python_implementation(),
                   docutils.__version__, docutils.__version_details__,
                   jinja2.__version__,
                   last_msgs)).encode('utf-8'))
    if app is not None:
        for extname, extmod in iteritems(app._extensions):
            modfile = getattr(extmod, '__file__', 'unknown')
            if isinstance(modfile, bytes):
                modfile = modfile.decode(fs_encoding, 'replace')
            os.write(fd, ('#   %s (%s) from %s\n' % (
                extname, app._extension_metadata[extname]['version'],
                modfile)).encode('utf-8'))
    os.write(fd, exc_format.encode('utf-8'))
    os.close(fd)
    return path


def get_module_source(modname):
    """Try to find the source code for a module.

    Can return ('file', 'filename') in which case the source is in the given
    file, or ('string', 'source') which which case the source is the string.
    """
    if modname not in sys.modules:
        try:
            __import__(modname)
        except Exception as err:
            raise PycodeError('error importing %r' % modname, err)
    mod = sys.modules[modname]
    filename = getattr(mod, '__file__', None)
    loader = getattr(mod, '__loader__', None)
    if loader and getattr(loader, 'get_filename', None):
        try:
            filename = loader.get_filename(modname)
        except Exception as err:
            raise PycodeError('error getting filename for %r' % filename, err)
    if filename is None and loader:
        try:
            return 'string', loader.get_source(modname)
        except Exception as err:
            raise PycodeError('error getting source for %r' % modname, err)
    if filename is None:
        raise PycodeError('no source found for module %r' % modname)
    filename = path.normpath(path.abspath(filename))
    lfilename = filename.lower()
    if lfilename.endswith('.pyo') or lfilename.endswith('.pyc'):
        filename = filename[:-1]
        if not path.isfile(filename) and path.isfile(filename + 'w'):
            filename += 'w'
    elif not (lfilename.endswith('.py') or lfilename.endswith('.pyw')):
        raise PycodeError('source is not a .py file: %r' % filename)
    if not path.isfile(filename):
        raise PycodeError('source file is not present: %r' % filename)
    return 'file', filename


def get_full_modname(modname, attribute):
    __import__(modname)
    module = sys.modules[modname]

    # Allow an attribute to have multiple parts and incidentially allow
    # repeated .s in the attribute.
    value = module
    for attr in attribute.split('.'):
        if attr:
            value = getattr(value, attr)

    return getattr(value, '__module__', None)


# a regex to recognize coding cookies
_coding_re = re.compile(r'coding[:=]\s*([-\w.]+)')


def detect_encoding(readline):
    """Like tokenize.detect_encoding() from Py3k, but a bit simplified."""

    def read_or_stop():
        try:
            return readline()
        except StopIteration:
            return None

    def get_normal_name(orig_enc):
        """Imitates get_normal_name in tokenizer.c."""
        # Only care about the first 12 characters.
        enc = orig_enc[:12].lower().replace('_', '-')
        if enc == 'utf-8' or enc.startswith('utf-8-'):
            return 'utf-8'
        if enc in ('latin-1', 'iso-8859-1', 'iso-latin-1') or \
           enc.startswith(('latin-1-', 'iso-8859-1-', 'iso-latin-1-')):
            return 'iso-8859-1'
        return orig_enc

    def find_cookie(line):
        try:
            line_string = line.decode('ascii')
        except UnicodeDecodeError:
            return None

        matches = _coding_re.findall(line_string)
        if not matches:
            return None
        return get_normal_name(matches[0])

    default = sys.getdefaultencoding()
    first = read_or_stop()
    if first and first.startswith(BOM_UTF8):
        first = first[3:]
        default = 'utf-8-sig'
    if not first:
        return default
    encoding = find_cookie(first)
    if encoding:
        return encoding
    second = read_or_stop()
    if not second:
        return default
    encoding = find_cookie(second)
    if encoding:
        return encoding
    return default


# Low-level utility functions and classes.

class Tee(object):
    """
    File-like object writing to two streams.
    """
    def __init__(self, stream1, stream2):
        self.stream1 = stream1
        self.stream2 = stream2

    def write(self, text):
        self.stream1.write(text)
        self.stream2.write(text)

    def flush(self):
        if hasattr(self.stream1, 'flush'):
            self.stream1.flush()
        if hasattr(self.stream2, 'flush'):
            self.stream2.flush()


def parselinenos(spec, total):
    """Parse a line number spec (such as "1,2,4-6") and return a list of
    wanted line numbers.
    """
    items = list()
    parts = spec.split(',')
    for part in parts:
        try:
            begend = part.strip().split('-')
            if len(begend) > 2:
                raise ValueError
            if len(begend) == 1:
                items.append(int(begend[0])-1)
            else:
                start = (begend[0] == '') and 0 or int(begend[0])-1
                end = (begend[1] == '') and total or int(begend[1])
                items.extend(range(start, end))
        except Exception:
            raise ValueError('invalid line number spec: %r' % spec)
    return items


def force_decode(string, encoding):
    """Forcibly get a unicode string out of a bytestring."""
    if isinstance(string, binary_type):
        try:
            if encoding:
                string = string.decode(encoding)
            else:
                # try decoding with utf-8, should only work for real UTF-8
                string = string.decode('utf-8')
        except UnicodeError:
            # last resort -- can't fail
            string = string.decode('latin1')
    return string


class attrdict(dict):
    def __getattr__(self, key):
        return self[key]

    def __setattr__(self, key, val):
        self[key] = val

    def __delattr__(self, key):
        del self[key]


def rpartition(s, t):
    """Similar to str.rpartition from 2.5, but doesn't return the separator."""
    i = s.rfind(t)
    if i != -1:
        return s[:i], s[i+len(t):]
    return '', s


def split_into(n, type, value):
    """Split an index entry into a given number of parts at semicolons."""
    parts = [x.strip() for x in value.split(';', n-1)]
    if sum(1 for part in parts if part) < n:
        raise ValueError('invalid %s index entry %r' % (type, value))
    return parts


def split_index_msg(type, value):
    # new entry types must be listed in directives/other.py!
    if type == 'single':
        try:
            result = split_into(2, 'single', value)
        except ValueError:
            result = split_into(1, 'single', value)
    elif type == 'pair':
        result = split_into(2, 'pair', value)
    elif type == 'triple':
        result = split_into(3, 'triple', value)
    elif type == 'see':
        result = split_into(2, 'see', value)
    elif type == 'seealso':
        result = split_into(2, 'see', value)
    else:
        raise ValueError('invalid %s index entry %r' % (type, value))

    return result


def format_exception_cut_frames(x=1):
    """Format an exception with traceback, but only the last x frames."""
    typ, val, tb = sys.exc_info()
    # res = ['Traceback (most recent call last):\n']
    res = []
    tbres = traceback.format_tb(tb)
    res += tbres[-x:]
    res += traceback.format_exception_only(typ, val)
    return ''.join(res)


class PeekableIterator(object):
    """
    An iterator which wraps any iterable and makes it possible to peek to see
    what's the next item.
    """
    def __init__(self, iterable):
        self.remaining = deque()
        self._iterator = iter(iterable)

    def __iter__(self):
        return self

    def __next__(self):
        """Return the next item from the iterator."""
        if self.remaining:
            return self.remaining.popleft()
        return next(self._iterator)

    next = __next__  # Python 2 compatibility

    def push(self, item):
        """Push the `item` on the internal stack, it will be returned on the
        next :meth:`next` call.
        """
        self.remaining.append(item)

    def peek(self):
        """Return the next item without changing the state of the iterator."""
        item = next(self)
        self.push(item)
        return item


def import_object(objname, source=None):
    try:
        module, name = objname.rsplit('.', 1)
    except ValueError as err:
        raise ExtensionError('Invalid full object name %s' % objname +
                             (source and ' (needed for %s)' % source or ''),
                             err)
    try:
        return getattr(__import__(module, None, None, [name]), name)
    except ImportError as err:
        raise ExtensionError('Could not import %s' % module +
                             (source and ' (needed for %s)' % source or ''),
                             err)
    except AttributeError as err:
        raise ExtensionError('Could not find %s' % objname +
                             (source and ' (needed for %s)' % source or ''),
                             err)


def encode_uri(uri):
    split = list(urlsplit(uri))
    split[1] = split[1].encode('idna').decode('ascii')
    split[2] = quote_plus(split[2].encode('utf-8'), '/').decode('ascii')
    query = list((q, quote_plus(v.encode('utf-8')))
                 for (q, v) in parse_qsl(split[3]))
    split[3] = urlencode(query).decode('ascii')
    return urlunsplit(split)


def split_docinfo(text):
    docinfo_re = re.compile('\A((?:\s*:\w+:.*?\n)+)', re.M)
    result = docinfo_re.split(text, 1)
    if len(result) == 1:
        return '', result[0]
    else:
        return result[1:]
