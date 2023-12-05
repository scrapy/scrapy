# -*- test-case-name: twisted.web.test.test_html -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""I hold HTML generation helpers.
"""

from html import escape
from io import StringIO

from incremental import Version

from twisted.python import log
from twisted.python.deprecate import deprecated


@deprecated(Version("Twisted", 15, 3, 0), replacement="twisted.web.template")
def PRE(text):
    "Wrap <pre> tags around some text and HTML-escape it."
    return "<pre>" + escape(text) + "</pre>"


@deprecated(Version("Twisted", 15, 3, 0), replacement="twisted.web.template")
def UL(lst):
    io = StringIO()
    io.write("<ul>\n")
    for el in lst:
        io.write("<li> %s</li>\n" % el)
    io.write("</ul>")
    return io.getvalue()


@deprecated(Version("Twisted", 15, 3, 0), replacement="twisted.web.template")
def linkList(lst):
    io = StringIO()
    io.write("<ul>\n")
    for hr, el in lst:
        io.write(f'<li> <a href="{hr}">{el}</a></li>\n')
    io.write("</ul>")
    return io.getvalue()


@deprecated(Version("Twisted", 15, 3, 0), replacement="twisted.web.template")
def output(func, *args, **kw):
    """output(func, *args, **kw) -> html string
    Either return the result of a function (which presumably returns an
    HTML-legal string) or a sparse HTMLized error message and a message
    in the server log.
    """
    try:
        return func(*args, **kw)
    except BaseException:
        log.msg(f"Error calling {func!r}:")
        log.err()
        return PRE("An error occurred.")
