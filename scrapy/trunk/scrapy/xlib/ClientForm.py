"""HTML form handling for web clients.

ClientForm is a Python module for handling HTML forms on the client
side, useful for parsing HTML forms, filling them in and returning the
completed forms to the server.  It has developed from a port of Gisle
Aas' Perl module HTML::Form, from the libwww-perl library, but the
interface is not the same.

The most useful docstring is the one for HTMLForm.

RFC 1866: HTML 2.0
RFC 1867: Form-based File Upload in HTML
RFC 2388: Returning Values from Forms: multipart/form-data
HTML 3.2 Specification, W3C Recommendation 14 January 1997 (for ISINDEX)
HTML 4.01 Specification, W3C Recommendation 24 December 1999


Copyright 2002-2007 John J. Lee <jjl@pobox.com>
Copyright 2005 Gary Poster
Copyright 2005 Zope Corporation
Copyright 1998-2000 Gisle Aas.

This code is free software; you can redistribute it and/or modify it
under the terms of the BSD or ZPL 2.1 licenses (see the file
COPYING.txt included with the distribution).

"""

# XXX
# Remove parser testing hack
# safeUrl()-ize action
# Switch to unicode throughout (would be 0.3.x)
#  See Wichert Akkerman's 2004-01-22 message to c.l.py.
# Add charset parameter to Content-type headers?  How to find value??
# Add some more functional tests
#  Especially single and multiple file upload on the internet.
#  Does file upload work when name is missing?  Sourceforge tracker form
#   doesn't like it.  Check standards, and test with Apache.  Test
#   binary upload with Apache.
# mailto submission & enctype text/plain
# I'm not going to fix this unless somebody tells me what real servers
#  that want this encoding actually expect: If enctype is
#  application/x-www-form-urlencoded and there's a FILE control present.
#  Strictly, it should be 'name=data' (see HTML 4.01 spec., section
#  17.13.2), but I send "name=" ATM.  What about multiple file upload??

# Would be nice, but I'm not going to do it myself:
# -------------------------------------------------
# Maybe a 0.4.x?
#   Replace by_label etc. with moniker / selector concept. Allows, eg.,
#    a choice between selection by value / id / label / element
#    contents.  Or choice between matching labels exactly or by
#    substring.  Etc.
#   Remove deprecated methods.
#   ...what else?
# Work on DOMForm.
# XForms?  Don't know if there's a need here.

__all__ = ['AmbiguityError', 'CheckboxControl', 'Control',
           'ControlNotFoundError', 'FileControl', 'FormParser', 'HTMLForm',
           'HiddenControl', 'IgnoreControl', 'ImageControl', 'IsindexControl',
           'Item', 'ItemCountError', 'ItemNotFoundError', 'Label',
           'ListControl', 'LocateError', 'Missing', 'ParseError', 'ParseFile',
           'ParseFileEx', 'ParseResponse', 'ParseResponseEx','PasswordControl',
           'RadioControl', 'ScalarControl', 'SelectControl',
           'SubmitButtonControl', 'SubmitControl', 'TextControl',
           'TextareaControl', 'XHTMLCompatibleFormParser']

try: True
except NameError:
    True = 1
    False = 0

try: bool
except NameError:
    def bool(expr):
        if expr: return True
        else: return False

try:
    import logging
    import inspect
except ImportError:
    def debug(msg, *args, **kwds):
        pass
else:
    _logger = logging.getLogger("ClientForm")
    OPTIMIZATION_HACK = True

    def debug(msg, *args, **kwds):
        if OPTIMIZATION_HACK:
            return

        caller_name = inspect.stack()[1][3]
        extended_msg = '%%s %s' % msg
        extended_args = (caller_name,)+args
        debug = _logger.debug(extended_msg, *extended_args, **kwds)

    def _show_debug_messages():
        global OPTIMIZATION_HACK
        OPTIMIZATION_HACK = False
        _logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        _logger.addHandler(handler)

import sys, urllib, urllib2, types, mimetools, copy, urlparse, \
       htmlentitydefs, re, random
from cStringIO import StringIO

import sgmllib
# monkeypatch to fix http://www.python.org/sf/803422 :-(
sgmllib.charref = re.compile("&#(x?[0-9a-fA-F]+)[^0-9a-fA-F]")

# HTMLParser.HTMLParser is recent, so live without it if it's not available
# (also, sgmllib.SGMLParser is much more tolerant of bad HTML)
try:
    import HTMLParser
except ImportError:
    HAVE_MODULE_HTMLPARSER = False
else:
    HAVE_MODULE_HTMLPARSER = True

try:
    import warnings
except ImportError:
    def deprecation(message, stack_offset=0):
        pass
else:
    def deprecation(message, stack_offset=0):
        warnings.warn(message, DeprecationWarning, stacklevel=3+stack_offset)

VERSION = "0.2.10"

CHUNK = 1024  # size of chunks fed to parser, in bytes

DEFAULT_ENCODING = "latin-1"

class Missing: pass

_compress_re = re.compile(r"\s+")
def compress_text(text): return _compress_re.sub(" ", text.strip())

def normalize_line_endings(text):
    return re.sub(r"(?:(?<!\r)\n)|(?:\r(?!\n))", "\r\n", text)


# This version of urlencode is from my Python 1.5.2 back-port of the
# Python 2.1 CVS maintenance branch of urllib.  It will accept a sequence
# of pairs instead of a mapping -- the 2.0 version only accepts a mapping.
def urlencode(query,doseq=False,):
    """Encode a sequence of two-element tuples or dictionary into a URL query \
string.

    If any values in the query arg are sequences and doseq is true, each
    sequence element is converted to a separate parameter.

    If the query arg is a sequence of two-element tuples, the order of the
    parameters in the output will match the order of parameters in the
    input.
    """

    if hasattr(query,"items"):
        # mapping objects
        query = query.items()
    else:
        # it's a bother at times that strings and string-like objects are
        # sequences...
        try:
            # non-sequence items should not work with len()
            x = len(query)
            # non-empty strings will fail this
            if len(query) and type(query[0]) != types.TupleType:
                raise TypeError()
            # zero-length sequences of all types will get here and succeed,
            # but that's a minor nit - since the original implementation
            # allowed empty dicts that type of behavior probably should be
            # preserved for consistency
        except TypeError:
            ty,va,tb = sys.exc_info()
            raise TypeError("not a valid non-string sequence or mapping "
                            "object", tb)

    l = []
    if not doseq:
        # preserve old behavior
        for k, v in query:
            k = urllib.quote_plus(str(k))
            v = urllib.quote_plus(str(v))
            l.append(k + '=' + v)
    else:
        for k, v in query:
            k = urllib.quote_plus(str(k))
            if type(v) == types.StringType:
                v = urllib.quote_plus(v)
                l.append(k + '=' + v)
            elif type(v) == types.UnicodeType:
                # is there a reasonable way to convert to ASCII?
                # encode generates a string, but "replace" or "ignore"
                # lose information and "strict" can raise UnicodeError
                v = urllib.quote_plus(v.encode("ASCII","replace"))
                l.append(k + '=' + v)
            else:
                try:
                    # is this a sufficient test for sequence-ness?
                    x = len(v)
                except TypeError:
                    # not a sequence
                    v = urllib.quote_plus(str(v))
                    l.append(k + '=' + v)
                else:
                    # loop over the sequence
                    for elt in v:
                        l.append(k + '=' + urllib.quote_plus(str(elt)))
    return '&'.join(l)

def unescape(data, entities, encoding=DEFAULT_ENCODING):
    if data is None or "&" not in data:
        return data

    def replace_entities(match, entities=entities, encoding=encoding):
        ent = match.group()
        if ent[1] == "#":
            return unescape_charref(ent[2:-1], encoding)

        repl = entities.get(ent)
        if repl is not None:
            if type(repl) != type(""):
                try:
                    repl = repl.encode(encoding)
                except UnicodeError:
                    repl = ent
        else:
            repl = ent

        return repl

    return re.sub(r"&#?[A-Za-z0-9]+?;", replace_entities, data)

def unescape_charref(data, encoding):
    name, base = data, 10
    if name.startswith("x"):
        name, base= name[1:], 16
    uc = unichr(int(name, base))
    if encoding is None:
        return uc
    else:
        try:
            repl = uc.encode(encoding)
        except UnicodeError:
            repl = "&#%s;" % data
        return repl

def get_entitydefs():
    import htmlentitydefs
    from codecs import latin_1_decode
    entitydefs = {}
    try:
        htmlentitydefs.name2codepoint
    except AttributeError:
        entitydefs = {}
        for name, char in htmlentitydefs.entitydefs.items():
            uc = latin_1_decode(char)[0]
            if uc.startswith("&#") and uc.endswith(";"):
                uc = unescape_charref(uc[2:-1], None)
            entitydefs["&%s;" % name] = uc
    else:
        for name, codepoint in htmlentitydefs.name2codepoint.items():
            entitydefs["&%s;" % name] = unichr(codepoint)
    return entitydefs


def issequence(x):
    try:
        x[0]
    except (TypeError, KeyError):
        return False
    except IndexError:
        pass
    return True

def isstringlike(x):
    try: x+""
    except: return False
    else: return True


def choose_boundary():
    """Return a string usable as a multipart boundary."""
    # follow IE and firefox
    nonce = "".join([str(random.randint(0, sys.maxint-1)) for i in 0,1,2])
    return "-"*27 + nonce

# This cut-n-pasted MimeWriter from standard library is here so can add
# to HTTP headers rather than message body when appropriate.  It also uses
# \r\n in place of \n.  This is a bit nasty.
class MimeWriter:

    """Generic MIME writer.

    Methods:

    __init__()
    addheader()
    flushheaders()
    startbody()
    startmultipartbody()
    nextpart()
    lastpart()

    A MIME writer is much more primitive than a MIME parser.  It
    doesn't seek around on the output file, and it doesn't use large
    amounts of buffer space, so you have to write the parts in the
    order they should occur on the output file.  It does buffer the
    headers you add, allowing you to rearrange their order.

    General usage is:

    f = <open the output file>
    w = MimeWriter(f)
    ...call w.addheader(key, value) 0 or more times...

    followed by either:

    f = w.startbody(content_type)
    ...call f.write(data) for body data...

    or:

    w.startmultipartbody(subtype)
    for each part:
        subwriter = w.nextpart()
        ...use the subwriter's methods to create the subpart...
    w.lastpart()

    The subwriter is another MimeWriter instance, and should be
    treated in the same way as the toplevel MimeWriter.  This way,
    writing recursive body parts is easy.

    Warning: don't forget to call lastpart()!

    XXX There should be more state so calls made in the wrong order
    are detected.

    Some special cases:

    - startbody() just returns the file passed to the constructor;
      but don't use this knowledge, as it may be changed.

    - startmultipartbody() actually returns a file as well;
      this can be used to write the initial 'if you can read this your
      mailer is not MIME-aware' message.

    - If you call flushheaders(), the headers accumulated so far are
      written out (and forgotten); this is useful if you don't need a
      body part at all, e.g. for a subpart of type message/rfc822
      that's (mis)used to store some header-like information.

    - Passing a keyword argument 'prefix=<flag>' to addheader(),
      start*body() affects where the header is inserted; 0 means
      append at the end, 1 means insert at the start; default is
      append for addheader(), but insert for start*body(), which use
      it to determine where the Content-type header goes.

    """

    def __init__(self, fp, http_hdrs=None):
        self._http_hdrs = http_hdrs
        self._fp = fp
        self._headers = []
        self._boundary = []
        self._first_part = True

    def addheader(self, key, value, prefix=0,
                  add_to_http_hdrs=0):
        """
        prefix is ignored if add_to_http_hdrs is true.
        """
        lines = value.split("\r\n")
        while lines and not lines[-1]: del lines[-1]
        while lines and not lines[0]: del lines[0]
        if add_to_http_hdrs:
            value = "".join(lines)
            # 2.2 urllib2 doesn't normalize header case
            self._http_hdrs.append((key.capitalize(), value))
        else:
            for i in range(1, len(lines)):
                lines[i] = "    " + lines[i].strip()
            value = "\r\n".join(lines) + "\r\n"
            line = key.title() + ": " + value
            if prefix:
                self._headers.insert(0, line)
            else:
                self._headers.append(line)

    def flushheaders(self):
        self._fp.writelines(self._headers)
        self._headers = []

    def startbody(self, ctype=None, plist=[], prefix=1,
                  add_to_http_hdrs=0, content_type=1):
        """
        prefix is ignored if add_to_http_hdrs is true.
        """
        if content_type and ctype:
            for name, value in plist:
                ctype = ctype + ';\r\n %s=%s' % (name, value)
            self.addheader("Content-Type", ctype, prefix=prefix,
                           add_to_http_hdrs=add_to_http_hdrs)
        self.flushheaders()
        if not add_to_http_hdrs: self._fp.write("\r\n")
        self._first_part = True
        return self._fp

    def startmultipartbody(self, subtype, boundary=None, plist=[], prefix=1,
                           add_to_http_hdrs=0, content_type=1):
        boundary = boundary or choose_boundary()
        self._boundary.append(boundary)
        return self.startbody("multipart/" + subtype,
                              [("boundary", boundary)] + plist,
                              prefix=prefix,
                              add_to_http_hdrs=add_to_http_hdrs,
                              content_type=content_type)

    def nextpart(self):
        boundary = self._boundary[-1]
        if self._first_part:
            self._first_part = False
        else:
            self._fp.write("\r\n")
        self._fp.write("--" + boundary + "\r\n")
        return self.__class__(self._fp)

    def lastpart(self):
        if self._first_part:
            self.nextpart()
        boundary = self._boundary.pop()
        self._fp.write("\r\n--" + boundary + "--\r\n")


class LocateError(ValueError): pass
class AmbiguityError(LocateError): pass
class ControlNotFoundError(LocateError): pass
class ItemNotFoundError(LocateError): pass

class ItemCountError(ValueError): pass

# for backwards compatibility, ParseError derives from exceptions that were
# raised by versions of ClientForm <= 0.2.5
if HAVE_MODULE_HTMLPARSER:
    SGMLLIB_PARSEERROR = sgmllib.SGMLParseError
    class ParseError(sgmllib.SGMLParseError,
                     HTMLParser.HTMLParseError,
                     ):
        pass
else:
    if hasattr(sgmllib, "SGMLParseError"):
        SGMLLIB_PARSEERROR = sgmllib.SGMLParseError
        class ParseError(sgmllib.SGMLParseError):
            pass
    else:
        SGMLLIB_PARSEERROR = RuntimeError
        class ParseError(RuntimeError):
            pass


class _AbstractFormParser:
    """forms attribute contains HTMLForm instances on completion."""
    # thanks to Moshe Zadka for an example of sgmllib/htmllib usage
    def __init__(self, entitydefs=None, encoding=DEFAULT_ENCODING):
        if entitydefs is None:
            entitydefs = get_entitydefs()
        self._entitydefs = entitydefs
        self._encoding = encoding

        self.base = None
        self.forms = []
        self.labels = []
        self._current_label = None
        self._current_form = None
        self._select = None
        self._optgroup = None
        self._option = None
        self._textarea = None

        # forms[0] will contain all controls that are outside of any form
        # self._global_form is an alias for self.forms[0]
        self._global_form = None
        self.start_form([])
        self.end_form()
        self._current_form = self._global_form = self.forms[0]

    def do_base(self, attrs):
        debug("%s", attrs)
        for key, value in attrs:
            if key == "href":
                self.base = self.unescape_attr_if_required(value)

    def end_body(self):
        debug("")
        if self._current_label is not None:
            self.end_label()
        if self._current_form is not self._global_form:
            self.end_form()

    def start_form(self, attrs):
        debug("%s", attrs)
        if self._current_form is not self._global_form:
            raise ParseError("nested FORMs")
        name = None
        action = None
        enctype = "application/x-www-form-urlencoded"
        method = "GET"
        d = {}
        for key, value in attrs:
            if key == "name":
                name = self.unescape_attr_if_required(value)
            elif key == "action":
                action = self.unescape_attr_if_required(value)
            elif key == "method":
                method = self.unescape_attr_if_required(value.upper())
            elif key == "enctype":
                enctype = self.unescape_attr_if_required(value.lower())
            d[key] = self.unescape_attr_if_required(value)
        controls = []
        self._current_form = (name, action, method, enctype), d, controls

    def end_form(self):
        debug("")
        if self._current_label is not None:
            self.end_label()
        if self._current_form is self._global_form:
            raise ParseError("end of FORM before start")
        self.forms.append(self._current_form)
        self._current_form = self._global_form

    def start_select(self, attrs):
        debug("%s", attrs)
        if self._select is not None:
            raise ParseError("nested SELECTs")
        if self._textarea is not None:
            raise ParseError("SELECT inside TEXTAREA")
        d = {}
        for key, val in attrs:
            d[key] = self.unescape_attr_if_required(val)

        self._select = d
        self._add_label(d)

        self._append_select_control({"__select": d})

    def end_select(self):
        debug("")
        if self._select is None:
            raise ParseError("end of SELECT before start")

        if self._option is not None:
            self._end_option()

        self._select = None

    def start_optgroup(self, attrs):
        debug("%s", attrs)
        if self._select is None:
            raise ParseError("OPTGROUP outside of SELECT")
        d = {}
        for key, val in attrs:
            d[key] = self.unescape_attr_if_required(val)

        self._optgroup = d

    def end_optgroup(self):
        debug("")
        if self._optgroup is None:
            raise ParseError("end of OPTGROUP before start")
        self._optgroup = None

    def _start_option(self, attrs):
        debug("%s", attrs)
        if self._select is None:
            raise ParseError("OPTION outside of SELECT")
        if self._option is not None:
            self._end_option()

        d = {}
        for key, val in attrs:
            d[key] = self.unescape_attr_if_required(val)

        self._option = {}
        self._option.update(d)
        if (self._optgroup and self._optgroup.has_key("disabled") and
            not self._option.has_key("disabled")):
            self._option["disabled"] = None

    def _end_option(self):
        debug("")
        if self._option is None:
            raise ParseError("end of OPTION before start")

        contents = self._option.get("contents", "").strip()
        self._option["contents"] = contents
        if not self._option.has_key("value"):
            self._option["value"] = contents
        if not self._option.has_key("label"):
            self._option["label"] = contents
        # stuff dict of SELECT HTML attrs into a special private key
        #  (gets deleted again later)
        self._option["__select"] = self._select
        self._append_select_control(self._option)
        self._option = None

    def _append_select_control(self, attrs):
        debug("%s", attrs)
        controls = self._current_form[2]
        name = self._select.get("name")
        controls.append(("select", name, attrs))

    def start_textarea(self, attrs):
        debug("%s", attrs)
        if self._textarea is not None:
            raise ParseError("nested TEXTAREAs")
        if self._select is not None:
            raise ParseError("TEXTAREA inside SELECT")
        d = {}
        for key, val in attrs:
            d[key] = self.unescape_attr_if_required(val)
        self._add_label(d)

        self._textarea = d

    def end_textarea(self):
        debug("")
        if self._textarea is None:
            raise ParseError("end of TEXTAREA before start")
        controls = self._current_form[2]
        name = self._textarea.get("name")
        controls.append(("textarea", name, self._textarea))
        self._textarea = None

    def start_label(self, attrs):
        debug("%s", attrs)
        if self._current_label:
            self.end_label()
        d = {}
        for key, val in attrs:
            d[key] = self.unescape_attr_if_required(val)
        taken = bool(d.get("for"))  # empty id is invalid
        d["__text"] = ""
        d["__taken"] = taken
        if taken:
            self.labels.append(d)
        self._current_label = d

    def end_label(self):
        debug("")
        label = self._current_label
        if label is None:
            # something is ugly in the HTML, but we're ignoring it
            return
        self._current_label = None
        # if it is staying around, it is True in all cases
        del label["__taken"]

    def _add_label(self, d):
        #debug("%s", d)
        if self._current_label is not None:
            if not self._current_label["__taken"]:
                self._current_label["__taken"] = True
                d["__label"] = self._current_label

    def handle_data(self, data):
        debug("%s", data)

        if self._option is not None:
            # self._option is a dictionary of the OPTION element's HTML
            # attributes, but it has two special keys, one of which is the
            # special "contents" key contains text between OPTION tags (the
            # other is the "__select" key: see the end_option method)
            map = self._option
            key = "contents"
        elif self._textarea is not None:
            map = self._textarea
            key = "value"
            data = normalize_line_endings(data)
        # not if within option or textarea
        elif self._current_label is not None:
            map = self._current_label
            key = "__text"
        else:
            return

        if data and not map.has_key(key):
            # according to
            # http://www.w3.org/TR/html4/appendix/notes.html#h-B.3.1 line break
            # immediately after start tags or immediately before end tags must
            # be ignored, but real browsers only ignore a line break after a
            # start tag, so we'll do that.
            if data[0:2] == "\r\n":
                data = data[2:]
            elif data[0:1] in ["\n", "\r"]:
                data = data[1:]
            map[key] = data
        else:
            map[key] = map[key] + data

    def do_button(self, attrs):
        debug("%s", attrs)
        d = {}
        d["type"] = "submit"  # default
        for key, val in attrs:
            d[key] = self.unescape_attr_if_required(val)
        controls = self._current_form[2]

        type = d["type"]
        name = d.get("name")
        # we don't want to lose information, so use a type string that
        # doesn't clash with INPUT TYPE={SUBMIT,RESET,BUTTON}
        # e.g. type for BUTTON/RESET is "resetbutton"
        #     (type for INPUT/RESET is "reset")
        type = type+"button"
        self._add_label(d)
        controls.append((type, name, d))

    def do_input(self, attrs):
        debug("%s", attrs)
        d = {}
        d["type"] = "text"  # default
        for key, val in attrs:
            d[key] = self.unescape_attr_if_required(val)
        controls = self._current_form[2]

        type = d["type"]
        name = d.get("name")
        self._add_label(d)
        controls.append((type, name, d))

    def do_isindex(self, attrs):
        debug("%s", attrs)
        d = {}
        for key, val in attrs:
            d[key] = self.unescape_attr_if_required(val)
        controls = self._current_form[2]

        self._add_label(d)
        # isindex doesn't have type or name HTML attributes
        controls.append(("isindex", None, d))

    def handle_entityref(self, name):
        #debug("%s", name)
        self.handle_data(unescape(
            '&%s;' % name, self._entitydefs, self._encoding))

    def handle_charref(self, name):
        #debug("%s", name)
        self.handle_data(unescape_charref(name, self._encoding))

    def unescape_attr(self, name):
        #debug("%s", name)
        return unescape(name, self._entitydefs, self._encoding)

    def unescape_attrs(self, attrs):
        #debug("%s", attrs)
        escaped_attrs = {}
        for key, val in attrs.items():
            try:
                val.items
            except AttributeError:
                escaped_attrs[key] = self.unescape_attr(val)
            else:
                # e.g. "__select" -- yuck!
                escaped_attrs[key] = self.unescape_attrs(val)
        return escaped_attrs

    def unknown_entityref(self, ref): self.handle_data("&%s;" % ref)
    def unknown_charref(self, ref): self.handle_data("&#%s;" % ref)


if not HAVE_MODULE_HTMLPARSER:
    class XHTMLCompatibleFormParser:
        def __init__(self, entitydefs=None, encoding=DEFAULT_ENCODING):
            raise ValueError("HTMLParser could not be imported")
else:
    class XHTMLCompatibleFormParser(_AbstractFormParser, HTMLParser.HTMLParser):
        """Good for XHTML, bad for tolerance of incorrect HTML."""
        # thanks to Michael Howitz for this!
        def __init__(self, entitydefs=None, encoding=DEFAULT_ENCODING):
            HTMLParser.HTMLParser.__init__(self)
            _AbstractFormParser.__init__(self, entitydefs, encoding)

        def feed(self, data):
            try:
                HTMLParser.HTMLParser.feed(self, data)
            except HTMLParser.HTMLParseError, exc:
                raise ParseError(exc)

        def start_option(self, attrs):
            _AbstractFormParser._start_option(self, attrs)

        def end_option(self):
            _AbstractFormParser._end_option(self)

        def handle_starttag(self, tag, attrs):
            try:
                method = getattr(self, "start_" + tag)
            except AttributeError:
                try:
                    method = getattr(self, "do_" + tag)
                except AttributeError:
                    pass  # unknown tag
                else:
                    method(attrs)
            else:
                method(attrs)

        def handle_endtag(self, tag):
            try:
                method = getattr(self, "end_" + tag)
            except AttributeError:
                pass  # unknown tag
            else:
                method()

        def unescape(self, name):
            # Use the entitydefs passed into constructor, not
            # HTMLParser.HTMLParser's entitydefs.
            return self.unescape_attr(name)

        def unescape_attr_if_required(self, name):
            return name  # HTMLParser.HTMLParser already did it
        def unescape_attrs_if_required(self, attrs):
            return attrs  # ditto

        def close(self):
            HTMLParser.HTMLParser.close(self)
            self.end_body()


class _AbstractSgmllibParser(_AbstractFormParser):

    def do_option(self, attrs):
        _AbstractFormParser._start_option(self, attrs)

    if sys.version_info[:2] >= (2,5):
        # we override this attr to decode hex charrefs
        entity_or_charref = re.compile(
            '&(?:([a-zA-Z][-.a-zA-Z0-9]*)|#(x?[0-9a-fA-F]+))(;?)')
        def convert_entityref(self, name):
            return unescape("&%s;" % name, self._entitydefs, self._encoding)
        def convert_charref(self, name):
            return unescape_charref("%s" % name, self._encoding)
        def unescape_attr_if_required(self, name):
            return name  # sgmllib already did it
        def unescape_attrs_if_required(self, attrs):
            return attrs  # ditto
    else:
        def unescape_attr_if_required(self, name):
            return self.unescape_attr(name)
        def unescape_attrs_if_required(self, attrs):
            return self.unescape_attrs(attrs)


class FormParser(_AbstractSgmllibParser, sgmllib.SGMLParser):
    """Good for tolerance of incorrect HTML, bad for XHTML."""
    def __init__(self, entitydefs=None, encoding=DEFAULT_ENCODING):
        sgmllib.SGMLParser.__init__(self)
        _AbstractFormParser.__init__(self, entitydefs, encoding)

    def feed(self, data):
        try:
            sgmllib.SGMLParser.feed(self, data)
        except SGMLLIB_PARSEERROR, exc:
            raise ParseError(exc)

    def close(self):
        sgmllib.SGMLParser.close(self)
        self.end_body()


# sigh, must support mechanize by allowing dynamic creation of classes based on
# its bundled copy of BeautifulSoup (which was necessary because of dependency
# problems)

def _create_bs_classes(bs,
                       icbinbs,
                       ):
    class _AbstractBSFormParser(_AbstractSgmllibParser):
        bs_base_class = None
        def __init__(self, entitydefs=None, encoding=DEFAULT_ENCODING):
            _AbstractFormParser.__init__(self, entitydefs, encoding)
            self.bs_base_class.__init__(self)
        def handle_data(self, data):
            _AbstractFormParser.handle_data(self, data)
            self.bs_base_class.handle_data(self, data)
        def feed(self, data):
            try:
                self.bs_base_class.feed(self, data)
            except SGMLLIB_PARSEERROR, exc:
                raise ParseError(exc)
        def close(self):
            self.bs_base_class.close(self)
            self.end_body()

    class RobustFormParser(_AbstractBSFormParser, bs):
        """Tries to be highly tolerant of incorrect HTML."""
        pass
    RobustFormParser.bs_base_class = bs
    class NestingRobustFormParser(_AbstractBSFormParser, icbinbs):
        """Tries to be highly tolerant of incorrect HTML.

        Different from RobustFormParser in that it more often guesses nesting
        above missing end tags (see BeautifulSoup docs).

        """
        pass
    NestingRobustFormParser.bs_base_class = icbinbs

    return RobustFormParser, NestingRobustFormParser

try:
    if sys.version_info[:2] < (2, 2):
        raise ImportError  # BeautifulSoup uses generators
    import BeautifulSoup
except ImportError:
    pass
else:
    RobustFormParser, NestingRobustFormParser = _create_bs_classes(
        BeautifulSoup.BeautifulSoup, BeautifulSoup.ICantBelieveItsBeautifulSoup
        )
    __all__ += ['RobustFormParser', 'NestingRobustFormParser']


#FormParser = XHTMLCompatibleFormParser  # testing hack
#FormParser = RobustFormParser  # testing hack


def ParseResponseEx(response,
                    select_default=False,
                    form_parser_class=FormParser,
                    request_class=urllib2.Request,
                    entitydefs=None,
                    encoding=DEFAULT_ENCODING,

                    # private
                    _urljoin=urlparse.urljoin,
                    _urlparse=urlparse.urlparse,
                    _urlunparse=urlparse.urlunparse,
                    ):
    """Identical to ParseResponse, except that:

    1. The returned list contains an extra item.  The first form in the list
    contains all controls not contained in any FORM element.

    2. The arguments ignore_errors and backwards_compat have been removed.

    3. Backwards-compatibility mode (backwards_compat=True) is not available.
    """
    return _ParseFileEx(response, response.geturl(),
                        select_default,
                        False,
                        form_parser_class,
                        request_class,
                        entitydefs,
                        False,
                        encoding,
                        _urljoin=_urljoin,
                        _urlparse=_urlparse,
                        _urlunparse=_urlunparse,
                        )

def ParseFileEx(file, base_uri,
                select_default=False,
                form_parser_class=FormParser,
                request_class=urllib2.Request,
                entitydefs=None,
                encoding=DEFAULT_ENCODING,

                # private
                _urljoin=urlparse.urljoin,
                _urlparse=urlparse.urlparse,
                _urlunparse=urlparse.urlunparse,
                ):
    """Identical to ParseFile, except that:

    1. The returned list contains an extra item.  The first form in the list
    contains all controls not contained in any FORM element.

    2. The arguments ignore_errors and backwards_compat have been removed.

    3. Backwards-compatibility mode (backwards_compat=True) is not available.
    """
    return _ParseFileEx(file, base_uri,
                        select_default,
                        False,
                        form_parser_class,
                        request_class,
                        entitydefs,
                        False,
                        encoding,
                        _urljoin=_urljoin,
                        _urlparse=_urlparse,
                        _urlunparse=_urlunparse,
                        )

def ParseResponse(response, *args, **kwds):
    """Parse HTTP response and return a list of HTMLForm instances.

    The return value of urllib2.urlopen can be conveniently passed to this
    function as the response parameter.

    ClientForm.ParseError is raised on parse errors.

    response: file-like object (supporting read() method) with a method
     geturl(), returning the URI of the HTTP response
    select_default: for multiple-selection SELECT controls and RADIO controls,
     pick the first item as the default if none are selected in the HTML
    form_parser_class: class to instantiate and use to pass
    request_class: class to return from .click() method (default is
     urllib2.Request)
    entitydefs: mapping like {"&amp;": "&", ...} containing HTML entity
     definitions (a sensible default is used)
    encoding: character encoding used for encoding numeric character references
     when matching link text.  ClientForm does not attempt to find the encoding
     in a META HTTP-EQUIV attribute in the document itself (mechanize, for
     example, does do that and will pass the correct value to ClientForm using
     this parameter).

    backwards_compat: boolean that determines whether the returned HTMLForm
     objects are backwards-compatible with old code.  If backwards_compat is
     true:

     - ClientForm 0.1 code will continue to work as before.

     - Label searches that do not specify a nr (number or count) will always
       get the first match, even if other controls match.  If
       backwards_compat is False, label searches that have ambiguous results
       will raise an AmbiguityError.

     - Item label matching is done by strict string comparison rather than
       substring matching.

     - De-selecting individual list items is allowed even if the Item is
       disabled.

    The backwards_compat argument will be deprecated in a future release.

    Pass a true value for select_default if you want the behaviour specified by
    RFC 1866 (the HTML 2.0 standard), which is to select the first item in a
    RADIO or multiple-selection SELECT control if none were selected in the
    HTML.  Most browsers (including Microsoft Internet Explorer (IE) and
    Netscape Navigator) instead leave all items unselected in these cases.  The
    W3C HTML 4.0 standard leaves this behaviour undefined in the case of
    multiple-selection SELECT controls, but insists that at least one RADIO
    button should be checked at all times, in contradiction to browser
    behaviour.

    There is a choice of parsers.  ClientForm.XHTMLCompatibleFormParser (uses
    HTMLParser.HTMLParser) works best for XHTML, ClientForm.FormParser (uses
    sgmllib.SGMLParser) (the default) works better for ordinary grubby HTML.
    Note that HTMLParser is only available in Python 2.2 and later.  You can
    pass your own class in here as a hack to work around bad HTML, but at your
    own risk: there is no well-defined interface.

    """
    return _ParseFileEx(response, response.geturl(), *args, **kwds)[1:]

def ParseFile(file, base_uri, *args, **kwds):
    """Parse HTML and return a list of HTMLForm instances.

    ClientForm.ParseError is raised on parse errors.

    file: file-like object (supporting read() method) containing HTML with zero
     or more forms to be parsed
    base_uri: the URI of the document (note that the base URI used to submit
     the form will be that given in the BASE element if present, not that of
     the document)

    For the other arguments and further details, see ParseResponse.__doc__.

    """
    return _ParseFileEx(file, base_uri, *args, **kwds)[1:]

def _ParseFileEx(file, base_uri,
                 select_default=False,
                 ignore_errors=False,
                 form_parser_class=FormParser,
                 request_class=urllib2.Request,
                 entitydefs=None,
                 backwards_compat=True,
                 encoding=DEFAULT_ENCODING,
                 _urljoin=urlparse.urljoin,
                 _urlparse=urlparse.urlparse,
                 _urlunparse=urlparse.urlunparse,
                 ):
    if backwards_compat:
        deprecation("operating in backwards-compatibility mode", 1)
    fp = form_parser_class(entitydefs, encoding)
    while 1:
        data = file.read(CHUNK)
        try:
            fp.feed(data)
        except ParseError, e:
            e.base_uri = base_uri
            raise
        if len(data) != CHUNK: break
    fp.close()
    if fp.base is not None:
        # HTML BASE element takes precedence over document URI
        base_uri = fp.base
    labels = []  # Label(label) for label in fp.labels]
    id_to_labels = {}
    for l in fp.labels:
        label = Label(l)
        labels.append(label)
        for_id = l["for"]
        coll = id_to_labels.get(for_id)
        if coll is None:
            id_to_labels[for_id] = [label]
        else:
            coll.append(label)
    forms = []
    for (name, action, method, enctype), attrs, controls in fp.forms:
        if action is None:
            action = base_uri
        else:
            action = _urljoin(base_uri, action)
        # would be nice to make HTMLForm class (form builder) pluggable
        form = HTMLForm(
            action, method, enctype, name, attrs, request_class,
            forms, labels, id_to_labels, backwards_compat)
        form._urlparse = _urlparse
        form._urlunparse = _urlunparse
        for ii in range(len(controls)):
            type, name, attrs = controls[ii]
            # index=ii*10 allows ImageControl to return multiple ordered pairs
            form.new_control(
                type, name, attrs, select_default=select_default, index=ii*10)
        forms.append(form)
    for form in forms:
        form.fixup()
    return forms


class Label:
    def __init__(self, attrs):
        self.id = attrs.get("for")
        self._text = attrs.get("__text").strip()
        self._ctext = compress_text(self._text)
        self.attrs = attrs
        self._backwards_compat = False  # maintained by HTMLForm

    def __getattr__(self, name):
        if name == "text":
            if self._backwards_compat:
                return self._text
            else:
                return self._ctext
        return getattr(Label, name)

    def __setattr__(self, name, value):
        if name == "text":
            # don't see any need for this, so make it read-only
            raise AttributeError("text attribute is read-only")
        self.__dict__[name] = value

    def __str__(self):
        return "<Label(id=%r, text=%r)>" % (self.id, self.text)


def _get_label(attrs):
    text = attrs.get("__label")
    if text is not None:
        return Label(text)
    else:
        return None

class Control:
    """An HTML form control.

    An HTMLForm contains a sequence of Controls.  The Controls in an HTMLForm
    are accessed using the HTMLForm.find_control method or the
    HTMLForm.controls attribute.

    Control instances are usually constructed using the ParseFile /
    ParseResponse functions.  If you use those functions, you can ignore the
    rest of this paragraph.  A Control is only properly initialised after the
    fixup method has been called.  In fact, this is only strictly necessary for
    ListControl instances.  This is necessary because ListControls are built up
    from ListControls each containing only a single item, and their initial
    value(s) can only be known after the sequence is complete.

    The types and values that are acceptable for assignment to the value
    attribute are defined by subclasses.

    If the disabled attribute is true, this represents the state typically
    represented by browsers by 'greying out' a control.  If the disabled
    attribute is true, the Control will raise AttributeError if an attempt is
    made to change its value.  In addition, the control will not be considered
    'successful' as defined by the W3C HTML 4 standard -- ie. it will
    contribute no data to the return value of the HTMLForm.click* methods.  To
    enable a control, set the disabled attribute to a false value.

    If the readonly attribute is true, the Control will raise AttributeError if
    an attempt is made to change its value.  To make a control writable, set
    the readonly attribute to a false value.

    All controls have the disabled and readonly attributes, not only those that
    may have the HTML attributes of the same names.

    On assignment to the value attribute, the following exceptions are raised:
    TypeError, AttributeError (if the value attribute should not be assigned
    to, because the control is disabled, for example) and ValueError.

    If the name or value attributes are None, or the value is an empty list, or
    if the control is disabled, the control is not successful.

    Public attributes:

    type: string describing type of control (see the keys of the
     HTMLForm.type2class dictionary for the allowable values) (readonly)
    name: name of control (readonly)
    value: current value of control (subclasses may allow a single value, a
     sequence of values, or either)
    disabled: disabled state
    readonly: readonly state
    id: value of id HTML attribute

    """
    def __init__(self, type, name, attrs, index=None):
        """
        type: string describing type of control (see the keys of the
         HTMLForm.type2class dictionary for the allowable values)
        name: control name
        attrs: HTML attributes of control's HTML element

        """
        raise NotImplementedError()

    def add_to_form(self, form):
        self._form = form
        form.controls.append(self)

    def fixup(self):
        pass

    def is_of_kind(self, kind):
        raise NotImplementedError()

    def clear(self):
        raise NotImplementedError()

    def __getattr__(self, name): raise NotImplementedError()
    def __setattr__(self, name, value): raise NotImplementedError()

    def pairs(self):
        """Return list of (key, value) pairs suitable for passing to urlencode.
        """
        return [(k, v) for (i, k, v) in self._totally_ordered_pairs()]

    def _totally_ordered_pairs(self):
        """Return list of (key, value, index) tuples.

        Like pairs, but allows preserving correct ordering even where several
        controls are involved.

        """
        raise NotImplementedError()

    def _write_mime_data(self, mw, name, value):
        """Write data for a subitem of this control to a MimeWriter."""
        # called by HTMLForm
        mw2 = mw.nextpart()
        mw2.addheader("Content-Disposition",
                      'form-data; name="%s"' % name, 1)
        f = mw2.startbody(prefix=0)
        f.write(value)

    def __str__(self):
        raise NotImplementedError()

    def get_labels(self):
        """Return all labels (Label instances) for this control.
        
        If the control was surrounded by a <label> tag, that will be the first
        label; all other labels, connected by 'for' and 'id', are in the order
        that appear in the HTML.

        """
        res = []
        if self._label:
            res.append(self._label)
        if self.id:
            res.extend(self._form._id_to_labels.get(self.id, ()))
        return res


#---------------------------------------------------
class ScalarControl(Control):
    """Control whose value is not restricted to one of a prescribed set.

    Some ScalarControls don't accept any value attribute.  Otherwise, takes a
    single value, which must be string-like.

    Additional read-only public attribute:

    attrs: dictionary mapping the names of original HTML attributes of the
     control to their values

    """
    def __init__(self, type, name, attrs, index=None):
        self._index = index
        self._label = _get_label(attrs)
        self.__dict__["type"] = type.lower()
        self.__dict__["name"] = name
        self._value = attrs.get("value")
        self.disabled = attrs.has_key("disabled")
        self.readonly = attrs.has_key("readonly")
        self.id = attrs.get("id")

        self.attrs = attrs.copy()

        self._clicked = False

        self._urlparse = urlparse.urlparse
        self._urlunparse = urlparse.urlunparse

    def __getattr__(self, name):
        if name == "value":
            return self.__dict__["_value"]
        else:
            raise AttributeError("%s instance has no attribute '%s'" %
                                 (self.__class__.__name__, name))

    def __setattr__(self, name, value):
        if name == "value":
            if not isstringlike(value):
                raise TypeError("must assign a string")
            elif self.readonly:
                raise AttributeError("control '%s' is readonly" % self.name)
            elif self.disabled:
                raise AttributeError("control '%s' is disabled" % self.name)
            self.__dict__["_value"] = value
        elif name in ("name", "type"):
            raise AttributeError("%s attribute is readonly" % name)
        else:
            self.__dict__[name] = value

    def _totally_ordered_pairs(self):
        name = self.name
        value = self.value
        if name is None or value is None or self.disabled:
            return []
        return [(self._index, name, value)]

    def clear(self):
        if self.readonly:
            raise AttributeError("control '%s' is readonly" % self.name)
        self.__dict__["_value"] = None

    def __str__(self):
        name = self.name
        value = self.value
        if name is None: name = "<None>"
        if value is None: value = "<None>"

        infos = []
        if self.disabled: infos.append("disabled")
        if self.readonly: infos.append("readonly")
        info = ", ".join(infos)
        if info: info = " (%s)" % info

        return "<%s(%s=%s)%s>" % (self.__class__.__name__, name, value, info)


#---------------------------------------------------
class TextControl(ScalarControl):
    """Textual input control.

    Covers:

    INPUT/TEXT
    INPUT/PASSWORD
    INPUT/HIDDEN
    TEXTAREA

    """
    def __init__(self, type, name, attrs, index=None):
        ScalarControl.__init__(self, type, name, attrs, index)
        if self.type == "hidden": self.readonly = True
        if self._value is None:
            self._value = ""

    def is_of_kind(self, kind): return kind == "text"

#---------------------------------------------------
class FileControl(ScalarControl):
    """File upload with INPUT TYPE=FILE.

    The value attribute of a FileControl is always None.  Use add_file instead.

    Additional public method: add_file

    """

    def __init__(self, type, name, attrs, index=None):
        ScalarControl.__init__(self, type, name, attrs, index)
        self._value = None
        self._upload_data = []

    def is_of_kind(self, kind): return kind == "file"

    def clear(self):
        if self.readonly:
            raise AttributeError("control '%s' is readonly" % self.name)
        self._upload_data = []

    def __setattr__(self, name, value):
        if name in ("value", "name", "type"):
            raise AttributeError("%s attribute is readonly" % name)
        else:
            self.__dict__[name] = value

    def add_file(self, file_object, content_type=None, filename=None):
        if not hasattr(file_object, "read"):
            raise TypeError("file-like object must have read method")
        if content_type is not None and not isstringlike(content_type):
            raise TypeError("content type must be None or string-like")
        if filename is not None and not isstringlike(filename):
            raise TypeError("filename must be None or string-like")
        if content_type is None:
            content_type = "application/octet-stream"
        self._upload_data.append((file_object, content_type, filename))

    def _totally_ordered_pairs(self):
        # XXX should it be successful even if unnamed?
        if self.name is None or self.disabled:
            return []
        return [(self._index, self.name, "")]

    def _write_mime_data(self, mw, _name, _value):
        # called by HTMLForm
        # assert _name == self.name and _value == ''
        if len(self._upload_data) < 2:
            if len(self._upload_data) == 0:
                file_object = StringIO()
                content_type = "application/octet-stream"
                filename = ""
            else:
                file_object, content_type, filename = self._upload_data[0]
                if filename is None:
                    filename = ""
            mw2 = mw.nextpart()
            fn_part = '; filename="%s"' % filename
            disp = 'form-data; name="%s"%s' % (self.name, fn_part)
            mw2.addheader("Content-Disposition", disp, prefix=1)
            fh = mw2.startbody(content_type, prefix=0)
            fh.write(file_object.read())
        else:
            # multiple files
            mw2 = mw.nextpart()
            disp = 'form-data; name="%s"' % self.name
            mw2.addheader("Content-Disposition", disp, prefix=1)
            fh = mw2.startmultipartbody("mixed", prefix=0)
            for file_object, content_type, filename in self._upload_data:
                mw3 = mw2.nextpart()
                if filename is None:
                    filename = ""
                fn_part = '; filename="%s"' % filename
                disp = "file%s" % fn_part
                mw3.addheader("Content-Disposition", disp, prefix=1)
                fh2 = mw3.startbody(content_type, prefix=0)
                fh2.write(file_object.read())
            mw2.lastpart()

    def __str__(self):
        name = self.name
        if name is None: name = "<None>"

        if not self._upload_data:
            value = "<No files added>"
        else:
            value = []
            for file, ctype, filename in self._upload_data:
                if filename is None:
                    value.append("<Unnamed file>")
                else:
                    value.append(filename)
            value = ", ".join(value)

        info = []
        if self.disabled: info.append("disabled")
        if self.readonly: info.append("readonly")
        info = ", ".join(info)
        if info: info = " (%s)" % info

        return "<%s(%s=%s)%s>" % (self.__class__.__name__, name, value, info)


#---------------------------------------------------
class IsindexControl(ScalarControl):
    """ISINDEX control.

    ISINDEX is the odd-one-out of HTML form controls.  In fact, it isn't really
    part of regular HTML forms at all, and predates it.  You're only allowed
    one ISINDEX per HTML document.  ISINDEX and regular form submission are
    mutually exclusive -- either submit a form, or the ISINDEX.

    Having said this, since ISINDEX controls may appear in forms (which is
    probably bad HTML), ParseFile / ParseResponse will include them in the
    HTMLForm instances it returns.  You can set the ISINDEX's value, as with
    any other control (but note that ISINDEX controls have no name, so you'll
    need to use the type argument of set_value!).  When you submit the form,
    the ISINDEX will not be successful (ie., no data will get returned to the
    server as a result of its presence), unless you click on the ISINDEX
    control, in which case the ISINDEX gets submitted instead of the form:

    form.set_value("my isindex value", type="isindex")
    urllib2.urlopen(form.click(type="isindex"))

    ISINDEX elements outside of FORMs are ignored.  If you want to submit one
    by hand, do it like so:

    url = urlparse.urljoin(page_uri, "?"+urllib.quote_plus("my isindex value"))
    result = urllib2.urlopen(url)

    """
    def __init__(self, type, name, attrs, index=None):
        ScalarControl.__init__(self, type, name, attrs, index)
        if self._value is None:
            self._value = ""

    def is_of_kind(self, kind): return kind in ["text", "clickable"]

    def _totally_ordered_pairs(self):
        return []

    def _click(self, form, coord, return_type, request_class=urllib2.Request):
        # Relative URL for ISINDEX submission: instead of "foo=bar+baz",
        # want "bar+baz".
        # This doesn't seem to be specified in HTML 4.01 spec. (ISINDEX is
        # deprecated in 4.01, but it should still say how to submit it).
        # Submission of ISINDEX is explained in the HTML 3.2 spec, though.
        parts = self._urlparse(form.action)
        rest, (query, frag) = parts[:-2], parts[-2:]
        parts = rest + (urllib.quote_plus(self.value), None)
        url = self._urlunparse(parts)
        req_data = url, None, []

        if return_type == "pairs":
            return []
        elif return_type == "request_data":
            return req_data
        else:
            return request_class(url)

    def __str__(self):
        value = self.value
        if value is None: value = "<None>"

        infos = []
        if self.disabled: infos.append("disabled")
        if self.readonly: infos.append("readonly")
        info = ", ".join(infos)
        if info: info = " (%s)" % info

        return "<%s(%s)%s>" % (self.__class__.__name__, value, info)


#---------------------------------------------------
class IgnoreControl(ScalarControl):
    """Control that we're not interested in.

    Covers:

    INPUT/RESET
    BUTTON/RESET
    INPUT/BUTTON
    BUTTON/BUTTON

    These controls are always unsuccessful, in the terminology of HTML 4 (ie.
    they never require any information to be returned to the server).

    BUTTON/BUTTON is used to generate events for script embedded in HTML.

    The value attribute of IgnoreControl is always None.

    """
    def __init__(self, type, name, attrs, index=None):
        ScalarControl.__init__(self, type, name, attrs, index)
        self._value = None

    def is_of_kind(self, kind): return False

    def __setattr__(self, name, value):
        if name == "value":
            raise AttributeError(
                "control '%s' is ignored, hence read-only" % self.name)
        elif name in ("name", "type"):
            raise AttributeError("%s attribute is readonly" % name)
        else:
            self.__dict__[name] = value


#---------------------------------------------------
# ListControls

# helpers and subsidiary classes

class Item:
    def __init__(self, control, attrs, index=None):
        label = _get_label(attrs)
        self.__dict__.update({
            "name": attrs["value"],
            "_labels": label and [label] or [],
            "attrs": attrs,
            "_control": control,
            "disabled": attrs.has_key("disabled"),
            "_selected": False,
            "id": attrs.get("id"),
            "_index": index,
            })
        control.items.append(self)

    def get_labels(self):
        """Return all labels (Label instances) for this item.
        
        For items that represent radio buttons or checkboxes, if the item was
        surrounded by a <label> tag, that will be the first label; all other
        labels, connected by 'for' and 'id', are in the order that appear in
        the HTML.
        
        For items that represent select options, if the option had a label
        attribute, that will be the first label.  If the option has contents
        (text within the option tags) and it is not the same as the label
        attribute (if any), that will be a label.  There is nothing in the
        spec to my knowledge that makes an option with an id unable to be the
        target of a label's for attribute, so those are included, if any, for
        the sake of consistency and completeness.

        """
        res = []
        res.extend(self._labels)
        if self.id:
            res.extend(self._control._form._id_to_labels.get(self.id, ()))
        return res

    def __getattr__(self, name):
        if name=="selected":
            return self._selected
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if name == "selected":
            self._control._set_selected_state(self, value)
        elif name == "disabled":
            self.__dict__["disabled"] = bool(value)
        else:
            raise AttributeError(name)

    def __str__(self):
        res = self.name
        if self.selected:
            res = "*" + res
        if self.disabled:
            res = "(%s)" % res
        return res

    def __repr__(self):
        # XXX appending the attrs without distinguishing them from name and id
        # is silly
        attrs = [("name", self.name), ("id", self.id)]+self.attrs.items()
        return "<%s %s>" % (
            self.__class__.__name__,
            " ".join(["%s=%r" % (k, v) for k, v in attrs])
            )

def disambiguate(items, nr, **kwds):
    msgs = []
    for key, value in kwds.items():
        msgs.append("%s=%r" % (key, value))
    msg = " ".join(msgs)
    if not items:
        raise ItemNotFoundError(msg)
    if nr is None:
        if len(items) > 1:
            raise AmbiguityError(msg)
        nr = 0
    if len(items) <= nr:
        raise ItemNotFoundError(msg)
    return items[nr]

class ListControl(Control):
    """Control representing a sequence of items.

    The value attribute of a ListControl represents the successful list items
    in the control.  The successful list items are those that are selected and
    not disabled.

    ListControl implements both list controls that take a length-1 value
    (single-selection) and those that take length >1 values
    (multiple-selection).

    ListControls accept sequence values only.  Some controls only accept
    sequences of length 0 or 1 (RADIO, and single-selection SELECT).
    In those cases, ItemCountError is raised if len(sequence) > 1.  CHECKBOXes
    and multiple-selection SELECTs (those having the "multiple" HTML attribute)
    accept sequences of any length.

    Note the following mistake:

    control.value = some_value
    assert control.value == some_value    # not necessarily true

    The reason for this is that the value attribute always gives the list items
    in the order they were listed in the HTML.

    ListControl items can also be referred to by their labels instead of names.
    Use the label argument to .get(), and the .set_value_by_label(),
    .get_value_by_label() methods.

    Note that, rather confusingly, though SELECT controls are represented in
    HTML by SELECT elements (which contain OPTION elements, representing
    individual list items), CHECKBOXes and RADIOs are not represented by *any*
    element.  Instead, those controls are represented by a collection of INPUT
    elements.  For example, this is a SELECT control, named "control1":

    <select name="control1">
     <option>foo</option>
     <option value="1">bar</option>
    </select>

    and this is a CHECKBOX control, named "control2":

    <input type="checkbox" name="control2" value="foo" id="cbe1">
    <input type="checkbox" name="control2" value="bar" id="cbe2">

    The id attribute of a CHECKBOX or RADIO ListControl is always that of its
    first element (for example, "cbe1" above).


    Additional read-only public attribute: multiple.

    """

    # ListControls are built up by the parser from their component items by
    # creating one ListControl per item, consolidating them into a single
    # master ListControl held by the HTMLForm:

    # -User calls form.new_control(...)
    # -Form creates Control, and calls control.add_to_form(self).
    # -Control looks for a Control with the same name and type in the form,
    #  and if it finds one, merges itself with that control by calling
    #  control.merge_control(self).  The first Control added to the form, of
    #  a particular name and type, is the only one that survives in the
    #  form.
    # -Form calls control.fixup for all its controls.  ListControls in the
    #  form know they can now safely pick their default values.

    # To create a ListControl without an HTMLForm, use:

    # control.merge_control(new_control)

    # (actually, it's much easier just to use ParseFile)

    _label = None

    def __init__(self, type, name, attrs={}, select_default=False,
                 called_as_base_class=False, index=None):
        """
        select_default: for RADIO and multiple-selection SELECT controls, pick
         the first item as the default if no 'selected' HTML attribute is
         present

        """
        if not called_as_base_class:
            raise NotImplementedError()

        self.__dict__["type"] = type.lower()
        self.__dict__["name"] = name
        self._value = attrs.get("value")
        self.disabled = False
        self.readonly = False
        self.id = attrs.get("id")
        self._closed = False

        # As Controls are merged in with .merge_control(), self.attrs will
        # refer to each Control in turn -- always the most recently merged
        # control.  Each merged-in Control instance corresponds to a single
        # list item: see ListControl.__doc__.
        self.items = []
        self._form = None

        self._select_default = select_default
        self._clicked = False

    def clear(self):
        self.value = []

    def is_of_kind(self, kind):
        if kind  == "list":
            return True
        elif kind == "multilist":
            return bool(self.multiple)
        elif kind == "singlelist":
            return not self.multiple
        else:
            return False

    def get_items(self, name=None, label=None, id=None,
                  exclude_disabled=False):
        """Return matching items by name or label.

        For argument docs, see the docstring for .get()

        """
        if name is not None and not isstringlike(name):
            raise TypeError("item name must be string-like")
        if label is not None and not isstringlike(label):
            raise TypeError("item label must be string-like")
        if id is not None and not isstringlike(id):
            raise TypeError("item id must be string-like")
        items = []  # order is important
        compat = self._form.backwards_compat
        for o in self.items:
            if exclude_disabled and o.disabled:
                continue
            if name is not None and o.name != name:
                continue
            if label is not None:
                for l in o.get_labels():
                    if ((compat and l.text == label) or
                        (not compat and l.text.find(label) > -1)):
                        break
                else:
                    continue
            if id is not None and o.id != id:
                continue
            items.append(o)
        return items

    def get(self, name=None, label=None, id=None, nr=None,
            exclude_disabled=False):
        """Return item by name or label, disambiguating if necessary with nr.

        All arguments must be passed by name, with the exception of 'name',
        which may be used as a positional argument.

        If name is specified, then the item must have the indicated name.

        If label is specified, then the item must have a label whose
        whitespace-compressed, stripped, text substring-matches the indicated
        label string (eg. label="please choose" will match
        "  Do  please  choose an item ").

        If id is specified, then the item must have the indicated id.

        nr is an optional 0-based index of the items matching the query.

        If nr is the default None value and more than item is found, raises
        AmbiguityError (unless the HTMLForm instance's backwards_compat
        attribute is true).

        If no item is found, or if items are found but nr is specified and not
        found, raises ItemNotFoundError.

        Optionally excludes disabled items.

        """
        if nr is None and self._form.backwards_compat:
            nr = 0  # :-/
        items = self.get_items(name, label, id, exclude_disabled)
        return disambiguate(items, nr, name=name, label=label, id=id)

    def _get(self, name, by_label=False, nr=None, exclude_disabled=False):
        # strictly for use by deprecated methods
        if by_label:
            name, label = None, name
        else:
            name, label = name, None
        return self.get(name, label, nr, exclude_disabled)

    def toggle(self, name, by_label=False, nr=None):
        """Deprecated: given a name or label and optional disambiguating index
        nr, toggle the matching item's selection.

        Selecting items follows the behavior described in the docstring of the
        'get' method.

        if the item is disabled, or this control is disabled or readonly,
        raise AttributeError.

        """
        deprecation(
            "item = control.get(...); item.selected = not item.selected")
        o = self._get(name, by_label, nr)
        self._set_selected_state(o, not o.selected)

    def set(self, selected, name, by_label=False, nr=None):
        """Deprecated: given a name or label and optional disambiguating index
        nr, set the matching item's selection to the bool value of selected.

        Selecting items follows the behavior described in the docstring of the
        'get' method.

        if the item is disabled, or this control is disabled or readonly,
        raise AttributeError.

        """
        deprecation(
            "control.get(...).selected = <boolean>")
        self._set_selected_state(self._get(name, by_label, nr), selected)

    def _set_selected_state(self, item, action):
        # action:
        # bool False: off
        # bool True: on
        if self.disabled:
            raise AttributeError("control '%s' is disabled" % self.name)
        if self.readonly:
            raise AttributeError("control '%s' is readonly" % self.name)
        action == bool(action)
        compat = self._form.backwards_compat
        if not compat and item.disabled:
            raise AttributeError("item is disabled")
        else:
            if compat and item.disabled and action:
                raise AttributeError("item is disabled")
            if self.multiple:
                item.__dict__["_selected"] = action
            else:
                if not action:
                    item.__dict__["_selected"] = False
                else:
                    for o in self.items:
                        o.__dict__["_selected"] = False
                    item.__dict__["_selected"] = True

    def toggle_single(self, by_label=None):
        """Deprecated: toggle the selection of the single item in this control.
        
        Raises ItemCountError if the control does not contain only one item.
        
        by_label argument is ignored, and included only for backwards
        compatibility.

        """
        deprecation(
            "control.items[0].selected = not control.items[0].selected")
        if len(self.items) != 1:
            raise ItemCountError(
                "'%s' is not a single-item control" % self.name)
        item = self.items[0]
        self._set_selected_state(item, not item.selected)

    def set_single(self, selected, by_label=None):
        """Deprecated: set the selection of the single item in this control.
        
        Raises ItemCountError if the control does not contain only one item.
        
        by_label argument is ignored, and included only for backwards
        compatibility.

        """
        deprecation(
            "control.items[0].selected = <boolean>")
        if len(self.items) != 1:
            raise ItemCountError(
                "'%s' is not a single-item control" % self.name)
        self._set_selected_state(self.items[0], selected)

    def get_item_disabled(self, name, by_label=False, nr=None):
        """Get disabled state of named list item in a ListControl."""
        deprecation(
            "control.get(...).disabled")
        return self._get(name, by_label, nr).disabled

    def set_item_disabled(self, disabled, name, by_label=False, nr=None):
        """Set disabled state of named list item in a ListControl.

        disabled: boolean disabled state

        """
        deprecation(
            "control.get(...).disabled = <boolean>")
        self._get(name, by_label, nr).disabled = disabled

    def set_all_items_disabled(self, disabled):
        """Set disabled state of all list items in a ListControl.

        disabled: boolean disabled state

        """
        for o in self.items:
            o.disabled = disabled

    def get_item_attrs(self, name, by_label=False, nr=None):
        """Return dictionary of HTML attributes for a single ListControl item.

        The HTML element types that describe list items are: OPTION for SELECT
        controls, INPUT for the rest.  These elements have HTML attributes that
        you may occasionally want to know about -- for example, the "alt" HTML
        attribute gives a text string describing the item (graphical browsers
        usually display this as a tooltip).

        The returned dictionary maps HTML attribute names to values.  The names
        and values are taken from the original HTML.

        """
        deprecation(
            "control.get(...).attrs")
        return self._get(name, by_label, nr).attrs

    def close_control(self):
        self._closed = True

    def add_to_form(self, form):
        assert self._form is None or form == self._form, (
            "can't add control to more than one form")
        self._form = form
        if self.name is None:
            # always count nameless elements as separate controls
            Control.add_to_form(self, form)
        else:
            for ii in range(len(form.controls)-1, -1, -1):
                control = form.controls[ii]
                if control.name == self.name and control.type == self.type:
                    if control._closed:
                        Control.add_to_form(self, form)
                    else:
                        control.merge_control(self)
                    break
            else:
                Control.add_to_form(self, form)

    def merge_control(self, control):
        assert bool(control.multiple) == bool(self.multiple)
        # usually, isinstance(control, self.__class__)
        self.items.extend(control.items)

    def fixup(self):
        """
        ListControls are built up from component list items (which are also
        ListControls) during parsing.  This method should be called after all
        items have been added.  See ListControl.__doc__ for the reason this is
        required.

        """
        # Need to set default selection where no item was indicated as being
        # selected by the HTML:

        # CHECKBOX:
        #  Nothing should be selected.
        # SELECT/single, SELECT/multiple and RADIO:
        #  RFC 1866 (HTML 2.0): says first item should be selected.
        #  W3C HTML 4.01 Specification: says that client behaviour is
        #   undefined in this case.  For RADIO, exactly one must be selected,
        #   though which one is undefined.
        #  Both Netscape and Microsoft Internet Explorer (IE) choose first
        #   item for SELECT/single.  However, both IE5 and Mozilla (both 1.0
        #   and Firebird 0.6) leave all items unselected for RADIO and
        #   SELECT/multiple.

        # Since both Netscape and IE all choose the first item for
        # SELECT/single, we do the same.  OTOH, both Netscape and IE
        # leave SELECT/multiple with nothing selected, in violation of RFC 1866
        # (but not in violation of the W3C HTML 4 standard); the same is true
        # of RADIO (which *is* in violation of the HTML 4 standard).  We follow
        # RFC 1866 if the _select_default attribute is set, and Netscape and IE
        # otherwise.  RFC 1866 and HTML 4 are always violated insofar as you
        # can deselect all items in a RadioControl.
        
        for o in self.items: 
            # set items' controls to self, now that we've merged
            o.__dict__["_control"] = self

    def __getattr__(self, name):
        if name == "value":
            compat = self._form.backwards_compat
            if self.name is None:
                return []
            return [o.name for o in self.items if o.selected and
                    (not o.disabled or compat)]
        else:
            raise AttributeError("%s instance has no attribute '%s'" %
                                 (self.__class__.__name__, name))

    def __setattr__(self, name, value):
        if name == "value":
            if self.disabled:
                raise AttributeError("control '%s' is disabled" % self.name)
            if self.readonly:
                raise AttributeError("control '%s' is readonly" % self.name)
            self._set_value(value)
        elif name in ("name", "type", "multiple"):
            raise AttributeError("%s attribute is readonly" % name)
        else:
            self.__dict__[name] = value

    def _set_value(self, value):
        if value is None or isstringlike(value):
            raise TypeError("ListControl, must set a sequence")
        if not value:
            compat = self._form.backwards_compat
            for o in self.items:
                if not o.disabled or compat:
                    o.selected = False
        elif self.multiple:
            self._multiple_set_value(value)
        elif len(value) > 1:
            raise ItemCountError(
                "single selection list, must set sequence of "
                "length 0 or 1")
        else:
            self._single_set_value(value)

    def _get_items(self, name, target=1):
        all_items = self.get_items(name)
        items = [o for o in all_items if not o.disabled]
        if len(items) < target:
            if len(all_items) < target:
                raise ItemNotFoundError(
                    "insufficient items with name %r" % name)
            else:
                raise AttributeError(
                    "insufficient non-disabled items with name %s" % name)
        on = []
        off = []
        for o in items:
            if o.selected:
                on.append(o)
            else:
                off.append(o)
        return on, off

    def _single_set_value(self, value):
        assert len(value) == 1
        on, off = self._get_items(value[0])
        assert len(on) <= 1
        if not on:
            off[0].selected = True

    def _multiple_set_value(self, value):
        compat = self._form.backwards_compat
        turn_on = []  # transactional-ish
        turn_off = [item for item in self.items if
                    item.selected and (not item.disabled or compat)]
        names = {}
        for nn in value:
            if nn in names.keys():
                names[nn] += 1
            else:
                names[nn] = 1
        for name, count in names.items():
            on, off = self._get_items(name, count)
            for i in range(count):
                if on:
                    item = on[0]
                    del on[0]
                    del turn_off[turn_off.index(item)]
                else:
                    item = off[0]
                    del off[0]
                    turn_on.append(item)
        for item in turn_off:
            item.selected = False
        for item in turn_on:
            item.selected = True

    def set_value_by_label(self, value):
        """Set the value of control by item labels.

        value is expected to be an iterable of strings that are substrings of
        the item labels that should be selected.  Before substring matching is
        performed, the original label text is whitespace-compressed
        (consecutive whitespace characters are converted to a single space
        character) and leading and trailing whitespace is stripped.  Ambiguous
        labels are accepted without complaint if the form's backwards_compat is
        True; otherwise, it will not complain as long as all ambiguous labels
        share the same item name (e.g. OPTION value).

        """
        if isstringlike(value):
            raise TypeError(value)
        if not self.multiple and len(value) > 1:
            raise ItemCountError(
                "single selection list, must set sequence of "
                "length 0 or 1")
        items = []
        for nn in value:
            found = self.get_items(label=nn)
            if len(found) > 1:
                if not self._form.backwards_compat:
                    # ambiguous labels are fine as long as item names (e.g.
                    # OPTION values) are same
                    opt_name = found[0].name
                    if [o for o in found[1:] if o.name != opt_name]:
                        raise AmbiguityError(nn)
                else:
                    # OK, we'll guess :-(  Assume first available item.
                    found = found[:1]
            for o in found:
                # For the multiple-item case, we could try to be smarter,
                # saving them up and trying to resolve, but that's too much.
                if self._form.backwards_compat or o not in items:
                    items.append(o)
                    break
            else:  # all of them are used
                raise ItemNotFoundError(nn)
        # now we have all the items that should be on
        # let's just turn everything off and then back on.
        self.value = []
        for o in items:
            o.selected = True

    def get_value_by_label(self):
        """Return the value of the control as given by normalized labels."""
        res = []
        compat = self._form.backwards_compat
        for o in self.items:
            if (not o.disabled or compat) and o.selected:
                for l in o.get_labels():
                    if l.text:
                        res.append(l.text)
                        break
                else:
                    res.append(None)
        return res

    def possible_items(self, by_label=False):
        """Deprecated: return the names or labels of all possible items.

        Includes disabled items, which may be misleading for some use cases.

        """
        deprecation(
            "[item.name for item in self.items]")
        if by_label:
            res = []
            for o in self.items:
                for l in o.get_labels():
                    if l.text:
                        res.append(l.text)
                        break
                else:
                    res.append(None)
            return res
        return [o.name for o in self.items]

    def _totally_ordered_pairs(self):
        if self.disabled or self.name is None:
            return []
        else:
            return [(o._index, self.name, o.name) for o in self.items
                    if o.selected and not o.disabled]

    def __str__(self):
        name = self.name
        if name is None: name = "<None>"

        display = [str(o) for o in self.items]

        infos = []
        if self.disabled: infos.append("disabled")
        if self.readonly: infos.append("readonly")
        info = ", ".join(infos)
        if info: info = " (%s)" % info

        return "<%s(%s=[%s])%s>" % (self.__class__.__name__,
                                    name, ", ".join(display), info)


class RadioControl(ListControl):
    """
    Covers:

    INPUT/RADIO

    """
    def __init__(self, type, name, attrs, select_default=False, index=None):
        attrs.setdefault("value", "on")
        ListControl.__init__(self, type, name, attrs, select_default,
                             called_as_base_class=True, index=index)
        self.__dict__["multiple"] = False
        o = Item(self, attrs, index)
        o.__dict__["_selected"] = attrs.has_key("checked")

    def fixup(self):
        ListControl.fixup(self)
        found = [o for o in self.items if o.selected and not o.disabled]
        if not found:
            if self._select_default:
                for o in self.items:
                    if not o.disabled:
                        o.selected = True
                        break
        else:
            # Ensure only one item selected.  Choose the last one,
            # following IE and Firefox.
            for o in found[:-1]:
                o.selected = False

    def get_labels(self):
        return []

class CheckboxControl(ListControl):
    """
    Covers:

    INPUT/CHECKBOX

    """
    def __init__(self, type, name, attrs, select_default=False, index=None):
        attrs.setdefault("value", "on")
        ListControl.__init__(self, type, name, attrs, select_default,
                             called_as_base_class=True, index=index)
        self.__dict__["multiple"] = True
        o = Item(self, attrs, index)
        o.__dict__["_selected"] = attrs.has_key("checked")

    def get_labels(self):
        return []


class SelectControl(ListControl):
    """
    Covers:

    SELECT (and OPTION)


    OPTION 'values', in HTML parlance, are Item 'names' in ClientForm parlance.

    SELECT control values and labels are subject to some messy defaulting
    rules.  For example, if the HTML representation of the control is:

    <SELECT name=year>
      <OPTION value=0 label="2002">current year</OPTION>
      <OPTION value=1>2001</OPTION>
      <OPTION>2000</OPTION>
    </SELECT>

    The items, in order, have labels "2002", "2001" and "2000", whereas their
    names (the OPTION values) are "0", "1" and "2000" respectively.  Note that
    the value of the last OPTION in this example defaults to its contents, as
    specified by RFC 1866, as do the labels of the second and third OPTIONs.

    The OPTION labels are sometimes more meaningful than the OPTION values,
    which can make for more maintainable code.

    Additional read-only public attribute: attrs

    The attrs attribute is a dictionary of the original HTML attributes of the
    SELECT element.  Other ListControls do not have this attribute, because in
    other cases the control as a whole does not correspond to any single HTML
    element.  control.get(...).attrs may be used as usual to get at the HTML
    attributes of the HTML elements corresponding to individual list items (for
    SELECT controls, these are OPTION elements).

    Another special case is that the Item.attrs dictionaries have a special key
    "contents" which does not correspond to any real HTML attribute, but rather
    contains the contents of the OPTION element:

    <OPTION>this bit</OPTION>

    """
    # HTML attributes here are treated slightly differently from other list
    # controls:
    # -The SELECT HTML attributes dictionary is stuffed into the OPTION
    #  HTML attributes dictionary under the "__select" key.
    # -The content of each OPTION element is stored under the special
    #  "contents" key of the dictionary.
    # After all this, the dictionary is passed to the SelectControl constructor
    # as the attrs argument, as usual.  However:
    # -The first SelectControl constructed when building up a SELECT control
    #  has a constructor attrs argument containing only the __select key -- so
    #  this SelectControl represents an empty SELECT control.
    # -Subsequent SelectControls have both OPTION HTML-attribute in attrs and
    #  the __select dictionary containing the SELECT HTML-attributes.

    def __init__(self, type, name, attrs, select_default=False, index=None):
        # fish out the SELECT HTML attributes from the OPTION HTML attributes
        # dictionary
        self.attrs = attrs["__select"].copy()
        self.__dict__["_label"] = _get_label(self.attrs)
        self.__dict__["id"] = self.attrs.get("id")
        self.__dict__["multiple"] = self.attrs.has_key("multiple")
        # the majority of the contents, label, and value dance already happened
        contents = attrs.get("contents")
        attrs = attrs.copy()
        del attrs["__select"]

        ListControl.__init__(self, type, name, self.attrs, select_default,
                             called_as_base_class=True, index=index)
        self.disabled = self.attrs.has_key("disabled")
        self.readonly = self.attrs.has_key("readonly")
        if attrs.has_key("value"):
            # otherwise it is a marker 'select started' token
            o = Item(self, attrs, index)
            o.__dict__["_selected"] = attrs.has_key("selected")
            # add 'label' label and contents label, if different.  If both are
            # provided, the 'label' label is used for display in HTML 
            # 4.0-compliant browsers (and any lower spec? not sure) while the
            # contents are used for display in older or less-compliant
            # browsers.  We make label objects for both, if the values are
            # different.
            label = attrs.get("label")
            if label:
                o._labels.append(Label({"__text": label}))
                if contents and contents != label:
                    o._labels.append(Label({"__text": contents}))
            elif contents:
                o._labels.append(Label({"__text": contents}))

    def fixup(self):
        ListControl.fixup(self)
        # Firefox doesn't exclude disabled items from those considered here
        # (i.e. from 'found', for both branches of the if below).  Note that
        # IE6 doesn't support the disabled attribute on OPTIONs at all.
        found = [o for o in self.items if o.selected]
        if not found:
            if not self.multiple or self._select_default:
                for o in self.items:
                    if not o.disabled:
                        was_disabled = self.disabled
                        self.disabled = False
                        try:
                            o.selected = True
                        finally:
                            o.disabled = was_disabled
                        break
        elif not self.multiple:
            # Ensure only one item selected.  Choose the last one,
            # following IE and Firefox.
            for o in found[:-1]:
                o.selected = False


#---------------------------------------------------
class SubmitControl(ScalarControl):
    """
    Covers:

    INPUT/SUBMIT
    BUTTON/SUBMIT

    """
    def __init__(self, type, name, attrs, index=None):
        ScalarControl.__init__(self, type, name, attrs, index)
        # IE5 defaults SUBMIT value to "Submit Query"; Firebird 0.6 leaves it
        # blank, Konqueror 3.1 defaults to "Submit".  HTML spec. doesn't seem
        # to define this.
        if self.value is None: self.value = ""
        self.readonly = True

    def get_labels(self):
        res = []
        if self.value:
            res.append(Label({"__text": self.value}))
        res.extend(ScalarControl.get_labels(self))
        return res

    def is_of_kind(self, kind): return kind == "clickable"

    def _click(self, form, coord, return_type, request_class=urllib2.Request):
        self._clicked = coord
        r = form._switch_click(return_type, request_class)
        self._clicked = False
        return r

    def _totally_ordered_pairs(self):
        if not self._clicked:
            return []
        return ScalarControl._totally_ordered_pairs(self)


#---------------------------------------------------
class ImageControl(SubmitControl):
    """
    Covers:

    INPUT/IMAGE

    Coordinates are specified using one of the HTMLForm.click* methods.

    """
    def __init__(self, type, name, attrs, index=None):
        SubmitControl.__init__(self, type, name, attrs, index)
        self.readonly = False

    def _totally_ordered_pairs(self):
        clicked = self._clicked
        if self.disabled or not clicked:
            return []
        name = self.name
        if name is None: return []
        pairs = [
            (self._index, "%s.x" % name, str(clicked[0])),
            (self._index+1, "%s.y" % name, str(clicked[1])),
            ]
        value = self._value
        if value:
            pairs.append((self._index+2, name, value))
        return pairs

    get_labels = ScalarControl.get_labels

# aliases, just to make str(control) and str(form) clearer
class PasswordControl(TextControl): pass
class HiddenControl(TextControl): pass
class TextareaControl(TextControl): pass
class SubmitButtonControl(SubmitControl): pass


def is_listcontrol(control): return control.is_of_kind("list")


class HTMLForm:
    """Represents a single HTML <form> ... </form> element.

    A form consists of a sequence of controls that usually have names, and
    which can take on various values.  The values of the various types of
    controls represent variously: text, zero-or-one-of-many or many-of-many
    choices, and files to be uploaded.  Some controls can be clicked on to
    submit the form, and clickable controls' values sometimes include the
    coordinates of the click.

    Forms can be filled in with data to be returned to the server, and then
    submitted, using the click method to generate a request object suitable for
    passing to urllib2.urlopen (or the click_request_data or click_pairs
    methods if you're not using urllib2).

    import ClientForm
    forms = ClientForm.ParseFile(html, base_uri)
    form = forms[0]

    form["query"] = "Python"
    form.find_control("nr_results").get("lots").selected = True

    response = urllib2.urlopen(form.click())

    Usually, HTMLForm instances are not created directly.  Instead, the
    ParseFile or ParseResponse factory functions are used.  If you do construct
    HTMLForm objects yourself, however, note that an HTMLForm instance is only
    properly initialised after the fixup method has been called (ParseFile and
    ParseResponse do this for you).  See ListControl.__doc__ for the reason
    this is required.

    Indexing a form (form["control_name"]) returns the named Control's value
    attribute.  Assignment to a form index (form["control_name"] = something)
    is equivalent to assignment to the named Control's value attribute.  If you
    need to be more specific than just supplying the control's name, use the
    set_value and get_value methods.

    ListControl values are lists of item names (specifically, the names of the
    items that are selected and not disabled, and hence are "successful" -- ie.
    cause data to be returned to the server).  The list item's name is the
    value of the corresponding HTML element's"value" attribute.

    Example:

      <INPUT type="CHECKBOX" name="cheeses" value="leicester"></INPUT>
      <INPUT type="CHECKBOX" name="cheeses" value="cheddar"></INPUT>

    defines a CHECKBOX control with name "cheeses" which has two items, named
    "leicester" and "cheddar".

    Another example:

      <SELECT name="more_cheeses">
        <OPTION>1</OPTION>
        <OPTION value="2" label="CHEDDAR">cheddar</OPTION>
      </SELECT>

    defines a SELECT control with name "more_cheeses" which has two items,
    named "1" and "2" (because the OPTION element's value HTML attribute
    defaults to the element contents -- see SelectControl.__doc__ for more on
    these defaulting rules).

    To select, deselect or otherwise manipulate individual list items, use the
    HTMLForm.find_control() and ListControl.get() methods.  To set the whole
    value, do as for any other control: use indexing or the set_/get_value
    methods.

    Example:

    # select *only* the item named "cheddar"
    form["cheeses"] = ["cheddar"]
    # select "cheddar", leave other items unaffected
    form.find_control("cheeses").get("cheddar").selected = True

    Some controls (RADIO and SELECT without the multiple attribute) can only
    have zero or one items selected at a time.  Some controls (CHECKBOX and
    SELECT with the multiple attribute) can have multiple items selected at a
    time.  To set the whole value of a ListControl, assign a sequence to a form
    index:

    form["cheeses"] = ["cheddar", "leicester"]

    If the ListControl is not multiple-selection, the assigned list must be of
    length one.

    To check if a control has an item, if an item is selected, or if an item is
    successful (selected and not disabled), respectively:

    "cheddar" in [item.name for item in form.find_control("cheeses").items]
    "cheddar" in [item.name for item in form.find_control("cheeses").items and
                  item.selected]
    "cheddar" in form["cheeses"]  # (or "cheddar" in form.get_value("cheeses"))

    Note that some list items may be disabled (see below).

    Note the following mistake:

    form[control_name] = control_value
    assert form[control_name] == control_value  # not necessarily true

    The reason for this is that form[control_name] always gives the list items
    in the order they were listed in the HTML.

    List items (hence list values, too) can be referred to in terms of list
    item labels rather than list item names using the appropriate label
    arguments.  Note that each item may have several labels.

    The question of default values of OPTION contents, labels and values is
    somewhat complicated: see SelectControl.__doc__ and
    ListControl.get_item_attrs.__doc__ if you think you need to know.

    Controls can be disabled or readonly.  In either case, the control's value
    cannot be changed until you clear those flags (see example below).
    Disabled is the state typically represented by browsers by 'greying out' a
    control.  Disabled controls are not 'successful' -- they don't cause data
    to get returned to the server.  Readonly controls usually appear in
    browsers as read-only text boxes.  Readonly controls are successful.  List
    items can also be disabled.  Attempts to select or deselect disabled items
    fail with AttributeError.

    If a lot of controls are readonly, it can be useful to do this:

    form.set_all_readonly(False)

    To clear a control's value attribute, so that it is not successful (until a
    value is subsequently set):

    form.clear("cheeses")

    More examples:

    control = form.find_control("cheeses")
    control.disabled = False
    control.readonly = False
    control.get("gruyere").disabled = True
    control.items[0].selected = True

    See the various Control classes for further documentation.  Many methods
    take name, type, kind, id, label and nr arguments to specify the control to
    be operated on: see HTMLForm.find_control.__doc__.

    ControlNotFoundError (subclass of ValueError) is raised if the specified
    control can't be found.  This includes occasions where a non-ListControl
    is found, but the method (set, for example) requires a ListControl.
    ItemNotFoundError (subclass of ValueError) is raised if a list item can't
    be found.  ItemCountError (subclass of ValueError) is raised if an attempt
    is made to select more than one item and the control doesn't allow that, or
    set/get_single are called and the control contains more than one item.
    AttributeError is raised if a control or item is readonly or disabled and
    an attempt is made to alter its value.

    Security note: Remember that any passwords you store in HTMLForm instances
    will be saved to disk in the clear if you pickle them (directly or
    indirectly).  The simplest solution to this is to avoid pickling HTMLForm
    objects.  You could also pickle before filling in any password, or just set
    the password to "" before pickling.


    Public attributes:

    action: full (absolute URI) form action
    method: "GET" or "POST"
    enctype: form transfer encoding MIME type
    name: name of form (None if no name was specified)
    attrs: dictionary mapping original HTML form attributes to their values

    controls: list of Control instances; do not alter this list
     (instead, call form.new_control to make a Control and add it to the
     form, or control.add_to_form if you already have a Control instance)



    Methods for form filling:
    -------------------------

    Most of the these methods have very similar arguments.  See
    HTMLForm.find_control.__doc__ for details of the name, type, kind, label
    and nr arguments.

    def find_control(self,
                     name=None, type=None, kind=None, id=None, predicate=None,
                     nr=None, label=None)

    get_value(name=None, type=None, kind=None, id=None, nr=None,
              by_label=False,  # by_label is deprecated
              label=None)
    set_value(value,
              name=None, type=None, kind=None, id=None, nr=None,
              by_label=False,  # by_label is deprecated
              label=None)

    clear_all()
    clear(name=None, type=None, kind=None, id=None, nr=None, label=None)

    set_all_readonly(readonly)


    Method applying only to FileControls:

    add_file(file_object,
             content_type="application/octet-stream", filename=None,
             name=None, id=None, nr=None, label=None)


    Methods applying only to clickable controls:

    click(name=None, type=None, id=None, nr=0, coord=(1,1), label=None)
    click_request_data(name=None, type=None, id=None, nr=0, coord=(1,1),
                       label=None)
    click_pairs(name=None, type=None, id=None, nr=0, coord=(1,1), label=None)

    """

    type2class = {
        "text": TextControl,
        "password": PasswordControl,
        "hidden": HiddenControl,
        "textarea": TextareaControl,

        "isindex": IsindexControl,

        "file": FileControl,

        "button": IgnoreControl,
        "buttonbutton": IgnoreControl,
        "reset": IgnoreControl,
        "resetbutton": IgnoreControl,

        "submit": SubmitControl,
        "submitbutton": SubmitButtonControl,
        "image": ImageControl,

        "radio": RadioControl,
        "checkbox": CheckboxControl,
        "select": SelectControl,
        }

#---------------------------------------------------
# Initialisation.  Use ParseResponse / ParseFile instead.

    def __init__(self, action, method="GET",
                 enctype="application/x-www-form-urlencoded",
                 name=None, attrs=None,
                 request_class=urllib2.Request,
                 forms=None, labels=None, id_to_labels=None,
                 backwards_compat=True):
        """
        In the usual case, use ParseResponse (or ParseFile) to create new
        HTMLForm objects.

        action: full (absolute URI) form action
        method: "GET" or "POST"
        enctype: form transfer encoding MIME type
        name: name of form
        attrs: dictionary mapping original HTML form attributes to their values

        """
        self.action = action
        self.method = method
        self.enctype = enctype
        self.name = name
        if attrs is not None:
            self.attrs = attrs.copy()
        else:
            self.attrs = {}
        self.controls = []
        self._request_class = request_class

        # these attributes are used by zope.testbrowser
        self._forms = forms  # this is a semi-public API!
        self._labels = labels  # this is a semi-public API!
        self._id_to_labels = id_to_labels  # this is a semi-public API!

        self.backwards_compat = backwards_compat  # note __setattr__

        self._urlunparse = urlparse.urlunparse
        self._urlparse = urlparse.urlparse

    def __getattr__(self, name):
        if name == "backwards_compat":
            return self._backwards_compat
        return getattr(HTMLForm, name)

    def __setattr__(self, name, value):
        # yuck
        if name == "backwards_compat":
            name = "_backwards_compat"
            value = bool(value)
            for cc in self.controls:
                try:
                    items = cc.items 
                except AttributeError:
                    continue
                else:
                    for ii in items:
                        for ll in ii.get_labels():
                            ll._backwards_compat = value
        self.__dict__[name] = value

    def new_control(self, type, name, attrs,
                    ignore_unknown=False, select_default=False, index=None):
        """Adds a new control to the form.

        This is usually called by ParseFile and ParseResponse.  Don't call it
        youself unless you're building your own Control instances.

        Note that controls representing lists of items are built up from
        controls holding only a single list item.  See ListControl.__doc__ for
        further information.

        type: type of control (see Control.__doc__ for a list)
        attrs: HTML attributes of control
        ignore_unknown: if true, use a dummy Control instance for controls of
         unknown type; otherwise, use a TextControl
        select_default: for RADIO and multiple-selection SELECT controls, pick
         the first item as the default if no 'selected' HTML attribute is
         present (this defaulting happens when the HTMLForm.fixup method is
         called)
        index: index of corresponding element in HTML (see
         MoreFormTests.test_interspersed_controls for motivation)

        """
        type = type.lower()
        klass = self.type2class.get(type)
        if klass is None:
            if ignore_unknown:
                klass = IgnoreControl
            else:
                klass = TextControl

        a = attrs.copy()
        if issubclass(klass, ListControl):
            control = klass(type, name, a, select_default, index)
        else:
            control = klass(type, name, a, index)

        if type == "select" and len(attrs) == 1:
            for ii in range(len(self.controls)-1, -1, -1):
                ctl = self.controls[ii]
                if ctl.type == "select":
                    ctl.close_control()
                    break

        control.add_to_form(self)
        control._urlparse = self._urlparse
        control._urlunparse = self._urlunparse

    def fixup(self):
        """Normalise form after all controls have been added.

        This is usually called by ParseFile and ParseResponse.  Don't call it
        youself unless you're building your own Control instances.

        This method should only be called once, after all controls have been
        added to the form.

        """
        for control in self.controls:
            control.fixup()
        self.backwards_compat = self._backwards_compat

#---------------------------------------------------
    def __str__(self):
        header = "%s%s %s %s" % (
            (self.name and self.name+" " or ""),
            self.method, self.action, self.enctype)
        rep = [header]
        for control in self.controls:
            rep.append("  %s" % str(control))
        return "<%s>" % "\n".join(rep)

#---------------------------------------------------
# Form-filling methods.

    def __getitem__(self, name):
        return self.find_control(name).value
    def __contains__(self, name):
        return bool(self.find_control(name))
    def __setitem__(self, name, value):
        control = self.find_control(name)
        try:
            control.value = value
        except AttributeError, e:
            raise ValueError(str(e))

    def get_value(self,
                  name=None, type=None, kind=None, id=None, nr=None,
                  by_label=False,  # by_label is deprecated
                  label=None):
        """Return value of control.

        If only name and value arguments are supplied, equivalent to

        form[name]

        """
        if by_label:
            deprecation("form.get_value_by_label(...)")
        c = self.find_control(name, type, kind, id, label=label, nr=nr)
        if by_label:
            try:
                meth = c.get_value_by_label
            except AttributeError:
                raise NotImplementedError(
                    "control '%s' does not yet support by_label" % c.name)
            else:
                return meth()
        else:
            return c.value
    def set_value(self, value,
                  name=None, type=None, kind=None, id=None, nr=None,
                  by_label=False,  # by_label is deprecated
                  label=None):
        """Set value of control.

        If only name and value arguments are supplied, equivalent to

        form[name] = value

        """
        if by_label:
            deprecation("form.get_value_by_label(...)")
        c = self.find_control(name, type, kind, id, label=label, nr=nr)
        if by_label:
            try:
                meth = c.set_value_by_label
            except AttributeError:
                raise NotImplementedError(
                    "control '%s' does not yet support by_label" % c.name)
            else:
                meth(value)
        else:
            c.value = value
    def get_value_by_label(
        self, name=None, type=None, kind=None, id=None, label=None, nr=None):
        """

        All arguments should be passed by name.

        """
        c = self.find_control(name, type, kind, id, label=label, nr=nr)
        return c.get_value_by_label()

    def set_value_by_label(
        self, value,
        name=None, type=None, kind=None, id=None, label=None, nr=None):
        """

        All arguments should be passed by name.

        """
        c = self.find_control(name, type, kind, id, label=label, nr=nr)
        c.set_value_by_label(value)

    def set_all_readonly(self, readonly):
        for control in self.controls:
            control.readonly = bool(readonly)

    def clear_all(self):
        """Clear the value attributes of all controls in the form.

        See HTMLForm.clear.__doc__.

        """
        for control in self.controls:
            control.clear()

    def clear(self,
              name=None, type=None, kind=None, id=None, nr=None, label=None):
        """Clear the value attribute of a control.

        As a result, the affected control will not be successful until a value
        is subsequently set.  AttributeError is raised on readonly controls.

        """
        c = self.find_control(name, type, kind, id, label=label, nr=nr)
        c.clear()


#---------------------------------------------------
# Form-filling methods applying only to ListControls.

    def possible_items(self,  # deprecated
                       name=None, type=None, kind=None, id=None,
                       nr=None, by_label=False, label=None):
        """Return a list of all values that the specified control can take."""
        c = self._find_list_control(name, type, kind, id, label, nr)
        return c.possible_items(by_label)

    def set(self, selected, item_name,  # deprecated
            name=None, type=None, kind=None, id=None, nr=None,
            by_label=False, label=None):
        """Select / deselect named list item.

        selected: boolean selected state

        """
        self._find_list_control(name, type, kind, id, label, nr).set(
            selected, item_name, by_label)
    def toggle(self, item_name,  # deprecated
               name=None, type=None, kind=None, id=None, nr=None,
               by_label=False, label=None):
        """Toggle selected state of named list item."""
        self._find_list_control(name, type, kind, id, label, nr).toggle(
            item_name, by_label)

    def set_single(self, selected,  # deprecated
                   name=None, type=None, kind=None, id=None,
                   nr=None, by_label=None, label=None):
        """Select / deselect list item in a control having only one item.

        If the control has multiple list items, ItemCountError is raised.

        This is just a convenience method, so you don't need to know the item's
        name -- the item name in these single-item controls is usually
        something meaningless like "1" or "on".

        For example, if a checkbox has a single item named "on", the following
        two calls are equivalent:

        control.toggle("on")
        control.toggle_single()

        """  # by_label ignored and deprecated
        self._find_list_control(
            name, type, kind, id, label, nr).set_single(selected)
    def toggle_single(self, name=None, type=None, kind=None, id=None,
                      nr=None, by_label=None, label=None):  # deprecated
        """Toggle selected state of list item in control having only one item.

        The rest is as for HTMLForm.set_single.__doc__.

        """  # by_label ignored and deprecated
        self._find_list_control(name, type, kind, id, label, nr).toggle_single()

#---------------------------------------------------
# Form-filling method applying only to FileControls.

    def add_file(self, file_object, content_type=None, filename=None,
                 name=None, id=None, nr=None, label=None):
        """Add a file to be uploaded.

        file_object: file-like object (with read method) from which to read
         data to upload
        content_type: MIME content type of data to upload
        filename: filename to pass to server

        If filename is None, no filename is sent to the server.

        If content_type is None, the content type is guessed based on the
        filename and the data from read from the file object.

        XXX
        At the moment, guessed content type is always application/octet-stream.
        Use sndhdr, imghdr modules.  Should also try to guess HTML, XML, and
        plain text.

        Note the following useful HTML attributes of file upload controls (see
        HTML 4.01 spec, section 17):

        accept: comma-separated list of content types that the server will
         handle correctly; you can use this to filter out non-conforming files
        size: XXX IIRC, this is indicative of whether form wants multiple or
         single files
        maxlength: XXX hint of max content length in bytes?

        """
        self.find_control(name, "file", id=id, label=label, nr=nr).add_file(
            file_object, content_type, filename)

#---------------------------------------------------
# Form submission methods, applying only to clickable controls.

    def click(self, name=None, type=None, id=None, nr=0, coord=(1,1),
              request_class=urllib2.Request,
              label=None):
        """Return request that would result from clicking on a control.

        The request object is a urllib2.Request instance, which you can pass to
        urllib2.urlopen (or ClientCookie.urlopen).

        Only some control types (INPUT/SUBMIT & BUTTON/SUBMIT buttons and
        IMAGEs) can be clicked.

        Will click on the first clickable control, subject to the name, type
        and nr arguments (as for find_control).  If no name, type, id or number
        is specified and there are no clickable controls, a request will be
        returned for the form in its current, un-clicked, state.

        IndexError is raised if any of name, type, id or nr is specified but no
        matching control is found.  ValueError is raised if the HTMLForm has an
        enctype attribute that is not recognised.

        You can optionally specify a coordinate to click at, which only makes a
        difference if you clicked on an image.

        """
        return self._click(name, type, id, label, nr, coord, "request",
                           self._request_class)

    def click_request_data(self,
                           name=None, type=None, id=None,
                           nr=0, coord=(1,1),
                           request_class=urllib2.Request,
                           label=None):
        """As for click method, but return a tuple (url, data, headers).

        You can use this data to send a request to the server.  This is useful
        if you're using httplib or urllib rather than urllib2.  Otherwise, use
        the click method.

        # Untested.  Have to subclass to add headers, I think -- so use urllib2
        # instead!
        import urllib
        url, data, hdrs = form.click_request_data()
        r = urllib.urlopen(url, data)

        # Untested.  I don't know of any reason to use httplib -- you can get
        # just as much control with urllib2.
        import httplib, urlparse
        url, data, hdrs = form.click_request_data()
        tup = urlparse(url)
        host, path = tup[1], urlparse.urlunparse((None, None)+tup[2:])
        conn = httplib.HTTPConnection(host)
        if data:
            httplib.request("POST", path, data, hdrs)
        else:
            httplib.request("GET", path, headers=hdrs)
        r = conn.getresponse()

        """
        return self._click(name, type, id, label, nr, coord, "request_data",
                           self._request_class)

    def click_pairs(self, name=None, type=None, id=None,
                    nr=0, coord=(1,1),
                    label=None):
        """As for click_request_data, but returns a list of (key, value) pairs.

        You can use this list as an argument to ClientForm.urlencode.  This is
        usually only useful if you're using httplib or urllib rather than
        urllib2 or ClientCookie.  It may also be useful if you want to manually
        tweak the keys and/or values, but this should not be necessary.
        Otherwise, use the click method.

        Note that this method is only useful for forms of MIME type
        x-www-form-urlencoded.  In particular, it does not return the
        information required for file upload.  If you need file upload and are
        not using urllib2, use click_request_data.

        Also note that Python 2.0's urllib.urlencode is slightly broken: it
        only accepts a mapping, not a sequence of pairs, as an argument.  This
        messes up any ordering in the argument.  Use ClientForm.urlencode
        instead.

        """
        return self._click(name, type, id, label, nr, coord, "pairs",
                           self._request_class)

#---------------------------------------------------

    def find_control(self,
                     name=None, type=None, kind=None, id=None,
                     predicate=None, nr=None,
                     label=None):
        """Locate and return some specific control within the form.

        At least one of the name, type, kind, predicate and nr arguments must
        be supplied.  If no matching control is found, ControlNotFoundError is
        raised.

        If name is specified, then the control must have the indicated name.

        If type is specified then the control must have the specified type (in
        addition to the types possible for <input> HTML tags: "text",
        "password", "hidden", "submit", "image", "button", "radio", "checkbox",
        "file" we also have "reset", "buttonbutton", "submitbutton",
        "resetbutton", "textarea", "select" and "isindex").

        If kind is specified, then the control must fall into the specified
        group, each of which satisfies a particular interface.  The types are
        "text", "list", "multilist", "singlelist", "clickable" and "file".

        If id is specified, then the control must have the indicated id.

        If predicate is specified, then the control must match that function.
        The predicate function is passed the control as its single argument,
        and should return a boolean value indicating whether the control
        matched.

        nr, if supplied, is the sequence number of the control (where 0 is the
        first).  Note that control 0 is the first control matching all the
        other arguments (if supplied); it is not necessarily the first control
        in the form.  If no nr is supplied, AmbiguityError is raised if
        multiple controls match the other arguments (unless the
        .backwards-compat attribute is true).

        If label is specified, then the control must have this label.  Note
        that radio controls and checkboxes never have labels: their items do.

        """
        if ((name is None) and (type is None) and (kind is None) and
            (id is None) and (label is None) and (predicate is None) and
            (nr is None)):
            raise ValueError(
                "at least one argument must be supplied to specify control")
        return self._find_control(name, type, kind, id, label, predicate, nr)

#---------------------------------------------------
# Private methods.

    def _find_list_control(self,
                           name=None, type=None, kind=None, id=None, 
                           label=None, nr=None):
        if ((name is None) and (type is None) and (kind is None) and
            (id is None) and (label is None) and (nr is None)):
            raise ValueError(
                "at least one argument must be supplied to specify control")

        return self._find_control(name, type, kind, id, label, 
                                  is_listcontrol, nr)

    def _find_control(self, name, type, kind, id, label, predicate, nr):
        if ((name is not None) and (name is not Missing) and
            not isstringlike(name)):
            raise TypeError("control name must be string-like")
        if (type is not None) and not isstringlike(type):
            raise TypeError("control type must be string-like")
        if (kind is not None) and not isstringlike(kind):
            raise TypeError("control kind must be string-like")
        if (id is not None) and not isstringlike(id):
            raise TypeError("control id must be string-like")
        if (label is not None) and not isstringlike(label):
            raise TypeError("control label must be string-like")
        if (predicate is not None) and not callable(predicate):
            raise TypeError("control predicate must be callable")
        if (nr is not None) and nr < 0:
            raise ValueError("control number must be a positive integer")

        orig_nr = nr
        found = None
        ambiguous = False
        if nr is None and self.backwards_compat:
            nr = 0

        for control in self.controls:
            if ((name is not None and name != control.name) and
                (name is not Missing or control.name is not None)):
                continue
            if type is not None and type != control.type:
                continue
            if kind is not None and not control.is_of_kind(kind):
                continue
            if id is not None and id != control.id:
                continue
            if predicate and not predicate(control):
                continue
            if label:
                for l in control.get_labels():
                    if l.text.find(label) > -1:
                        break
                else:
                    continue
            if nr is not None:
                if nr == 0:
                    return control  # early exit: unambiguous due to nr
                nr -= 1
                continue
            if found:
                ambiguous = True
                break
            found = control

        if found and not ambiguous:
            return found

        description = []
        if name is not None: description.append("name %s" % repr(name))
        if type is not None: description.append("type '%s'" % type)
        if kind is not None: description.append("kind '%s'" % kind)
        if id is not None: description.append("id '%s'" % id)
        if label is not None: description.append("label '%s'" % label)
        if predicate is not None:
            description.append("predicate %s" % predicate)
        if orig_nr: description.append("nr %d" % orig_nr)
        description = ", ".join(description)

        if ambiguous:
            raise AmbiguityError("more than one control matching "+description)
        elif not found:
            raise ControlNotFoundError("no control matching "+description)
        assert False

    def _click(self, name, type, id, label, nr, coord, return_type,
               request_class=urllib2.Request):
        try:
            control = self._find_control(
                name, type, "clickable", id, label, None, nr)
        except ControlNotFoundError:
            if ((name is not None) or (type is not None) or (id is not None) or
                (nr != 0)):
                raise
            # no clickable controls, but no control was explicitly requested,
            # so return state without clicking any control
            return self._switch_click(return_type, request_class)
        else:
            return control._click(self, coord, return_type, request_class)

    def _pairs(self):
        """Return sequence of (key, value) pairs suitable for urlencoding."""
        return [(k, v) for (i, k, v, c_i) in self._pairs_and_controls()]


    def _pairs_and_controls(self):
        """Return sequence of (index, key, value, control_index)
        of totally ordered pairs suitable for urlencoding.

        control_index is the index of the control in self.controls
        """
        pairs = []
        for control_index in range(len(self.controls)):
            control = self.controls[control_index]
            for ii, key, val in control._totally_ordered_pairs():
                pairs.append((ii, key, val, control_index))

        # stable sort by ONLY first item in tuple
        pairs.sort()

        return pairs

    def _request_data(self):
        """Return a tuple (url, data, headers)."""
        method = self.method.upper()
        #scheme, netloc, path, parameters, query, frag = urlparse.urlparse(self.action)
        parts = self._urlparse(self.action)
        rest, (query, frag) = parts[:-2], parts[-2:]

        if method == "GET":
            if self.enctype != "application/x-www-form-urlencoded":
                raise ValueError(
                    "unknown GET form encoding type '%s'" % self.enctype)
            parts = rest + (urlencode(self._pairs()), None)
            uri = self._urlunparse(parts)
            return uri, None, []
        elif method == "POST":
            parts = rest + (query, None)
            uri = self._urlunparse(parts)
            if self.enctype == "application/x-www-form-urlencoded":
                return (uri, urlencode(self._pairs()),
                        [("Content-Type", self.enctype)])
            elif self.enctype == "multipart/form-data":
                data = StringIO()
                http_hdrs = []
                mw = MimeWriter(data, http_hdrs)
                f = mw.startmultipartbody("form-data", add_to_http_hdrs=True,
                                          prefix=0)
                for ii, k, v, control_index in self._pairs_and_controls():
                    self.controls[control_index]._write_mime_data(mw, k, v)
                mw.lastpart()
                return uri, data.getvalue(), http_hdrs
            else:
                raise ValueError(
                    "unknown POST form encoding type '%s'" % self.enctype)
        else:
            raise ValueError("Unknown method '%s'" % method)

    def _switch_click(self, return_type, request_class=urllib2.Request):
        # This is called by HTMLForm and clickable Controls to hide switching
        # on return_type.
        if return_type == "pairs":
            return self._pairs()
        elif return_type == "request_data":
            return self._request_data()
        else:
            req_data = self._request_data()
            req = request_class(req_data[0], req_data[1])
            for key, val in req_data[2]:
                add_hdr = req.add_header
                if key.lower() == "content-type":
                    try:
                        add_hdr = req.add_unredirected_header
                    except AttributeError:
                        # pre-2.4 and not using ClientCookie
                        pass
                add_hdr(key, val)
            return req
