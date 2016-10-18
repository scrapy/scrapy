# -*- coding: utf-8 -*-
"""
    sphinx.util.pycompat
    ~~~~~~~~~~~~~~~~~~~~

    Stuff for Python version compatibility.

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import io
import sys
import codecs
import warnings

from six import class_types
from six.moves import zip_longest
from itertools import product

from six import PY3, text_type, exec_

NoneType = type(None)

# ------------------------------------------------------------------------------
# Python 2/3 compatibility

if PY3:
    # Python 3
    # prefix for Unicode strings
    u = ''
    from io import TextIOWrapper

    # safely encode a string for printing to the terminal
    def terminal_safe(s):
        return s.encode('ascii', 'backslashreplace').decode('ascii')
    # some kind of default system encoding; should be used with a lenient
    # error handler
    sys_encoding = sys.getdefaultencoding()

    # support for running 2to3 over config files
    def convert_with_2to3(filepath):
        from lib2to3.refactor import RefactoringTool, get_fixers_from_package
        from lib2to3.pgen2.parse import ParseError
        fixers = get_fixers_from_package('lib2to3.fixes')
        refactoring_tool = RefactoringTool(fixers)
        source = refactoring_tool._read_python_source(filepath)[0]
        try:
            tree = refactoring_tool.refactor_string(source, 'conf.py')
        except ParseError as err:
            # do not propagate lib2to3 exceptions
            lineno, offset = err.context[1]
            # try to match ParseError details with SyntaxError details
            raise SyntaxError(err.msg, (filepath, lineno, offset, err.value))
        return text_type(tree)
    from html import escape as htmlescape  # noqa: >= Python 3.2

    class UnicodeMixin:
        """Mixin class to handle defining the proper __str__/__unicode__
        methods in Python 2 or 3."""

        def __str__(self):
            return self.__unicode__()

    from textwrap import indent

else:
    # Python 2
    u = 'u'
    # no need to refactor on 2.x versions
    convert_with_2to3 = None

    def TextIOWrapper(stream, encoding):
        return codecs.lookup(encoding or 'ascii')[2](stream)

    # safely encode a string for printing to the terminal
    def terminal_safe(s):
        return s.encode('ascii', 'backslashreplace')
    # some kind of default system encoding; should be used with a lenient
    # error handler
    sys_encoding = __import__('locale').getpreferredencoding()
    # use Python 3 name
    from cgi import escape as htmlescape  # noqa: F401

    class UnicodeMixin(object):
        """Mixin class to handle defining the proper __str__/__unicode__
        methods in Python 2 or 3."""

        def __str__(self):
            return self.__unicode__().encode('utf8')

    # backport from python3
    def indent(text, prefix, predicate=None):
        if predicate is None:
            def predicate(line):
                return line.strip()

        def prefixed_lines():
            for line in text.splitlines(True):
                yield (prefix + line if predicate(line) else line)
        return ''.join(prefixed_lines())


def execfile_(filepath, _globals, open=open):
    from sphinx.util.osutil import fs_encoding
    # get config source -- 'b' is a no-op under 2.x, while 'U' is
    # ignored under 3.x (but 3.x compile() accepts \r\n newlines)
    f = open(filepath, 'rbU')
    try:
        source = f.read()
    finally:
        f.close()

    # py26 accept only LF eol instead of CRLF
    if sys.version_info[:2] == (2, 6):
        source = source.replace(b'\r\n', b'\n')

    # compile to a code object, handle syntax errors
    filepath_enc = filepath.encode(fs_encoding)
    try:
        code = compile(source, filepath_enc, 'exec')
    except SyntaxError:
        if convert_with_2to3:
            # maybe the file uses 2.x syntax; try to refactor to
            # 3.x syntax using 2to3
            source = convert_with_2to3(filepath)
            code = compile(source, filepath_enc, 'exec')
        else:
            raise
    exec_(code, _globals)

# ------------------------------------------------------------------------------
# Internal module backwards-compatibility


class _DeprecationWrapper(object):
    def __init__(self, mod, deprecated):
        self._mod = mod
        self._deprecated = deprecated

    def __getattr__(self, attr):
        if attr in self._deprecated:
            warnings.warn("sphinx.util.pycompat.%s is deprecated and will be "
                          "removed in Sphinx 1.4, please use the standard "
                          "library version instead." % attr,
                          DeprecationWarning, stacklevel=2)
            return self._deprecated[attr]
        return getattr(self._mod, attr)

sys.modules[__name__] = _DeprecationWrapper(sys.modules[__name__], dict(
    zip_longest = zip_longest,
    product = product,
    all = all,
    any = any,
    next = next,
    open = open,
    class_types = class_types,
    base_exception = BaseException,
    relpath = __import__('os').path.relpath,
    StringIO = io.StringIO,
    BytesIO = io.BytesIO,
))
