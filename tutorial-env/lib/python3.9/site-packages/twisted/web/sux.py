# -*- test-case-name: twisted.web.test.test_xml -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
*S*mall, *U*ncomplicated *X*ML.

This is a very simple implementation of XML/HTML as a network
protocol.  It is not at all clever.  Its main features are that it
does not:

  - support namespaces
  - mung mnemonic entity references
  - validate
  - perform *any* external actions (such as fetching URLs or writing files)
    under *any* circumstances
  - has lots and lots of horrible hacks for supporting broken HTML (as an
    option, they're not on by default).
"""


from twisted.internet.protocol import Protocol
from twisted.python.reflect import prefixedMethodNames

# Elements of the three-tuples in the state table.
BEGIN_HANDLER = 0
DO_HANDLER = 1
END_HANDLER = 2

identChars = ".-_:"
lenientIdentChars = identChars + ";+#/%~"


def nop(*args, **kw):
    "Do nothing."


def unionlist(*args):
    l = []
    for x in args:
        l.extend(x)
    d = {x: 1 for x in l}
    return d.keys()


def zipfndict(*args, **kw):
    default = kw.get("default", nop)
    d = {}
    for key in unionlist(*(fndict.keys() for fndict in args)):
        d[key] = tuple(x.get(key, default) for x in args)
    return d


def prefixedMethodClassDict(clazz, prefix):
    return {
        name: getattr(clazz, prefix + name)
        for name in prefixedMethodNames(clazz, prefix)
    }


def prefixedMethodObjDict(obj, prefix):
    return {
        name: getattr(obj, prefix + name)
        for name in prefixedMethodNames(obj.__class__, prefix)
    }


class ParseError(Exception):
    def __init__(self, filename, line, col, message):
        self.filename = filename
        self.line = line
        self.col = col
        self.message = message

    def __str__(self) -> str:
        return f"{self.filename}:{self.line}:{self.col}: {self.message}"


class XMLParser(Protocol):

    state = None
    encodings = None
    filename = "<xml />"
    beExtremelyLenient = 0
    _prepend = None

    # _leadingBodyData will sometimes be set before switching to the
    # 'bodydata' state, when we "accidentally" read a byte of bodydata
    # in a different state.
    _leadingBodyData = None

    def connectionMade(self):
        self.lineno = 1
        self.colno = 0
        self.encodings = []

    def saveMark(self):
        """Get the line number and column of the last character parsed"""
        # This gets replaced during dataReceived, restored afterwards
        return (self.lineno, self.colno)

    def _parseError(self, message):
        raise ParseError(*((self.filename,) + self.saveMark() + (message,)))

    def _buildStateTable(self):
        """Return a dictionary of begin, do, end state function tuples"""
        # _buildStateTable leaves something to be desired but it does what it
        # does.. probably slowly, so I'm doing some evil caching so it doesn't
        # get called more than once per class.
        stateTable = getattr(self.__class__, "__stateTable", None)
        if stateTable is None:
            stateTable = self.__class__.__stateTable = zipfndict(
                *(
                    prefixedMethodObjDict(self, prefix)
                    for prefix in ("begin_", "do_", "end_")
                )
            )
        return stateTable

    def _decode(self, data):
        if "UTF-16" in self.encodings or "UCS-2" in self.encodings:
            assert not len(data) & 1, "UTF-16 must come in pairs for now"
        if self._prepend:
            data = self._prepend + data
        for encoding in self.encodings:
            data = str(data, encoding)
        return data

    def maybeBodyData(self):
        if self.endtag:
            return "bodydata"

        # Get ready for fun! We're going to allow
        # <script>if (foo < bar)</script> to work!
        # We do this by making everything between <script> and
        # </script> a Text
        # BUT <script src="foo"> will be special-cased to do regular,
        # lenient behavior, because those may not have </script>
        # -radix

        if self.tagName == "script" and "src" not in self.tagAttributes:
            # we do this ourselves rather than having begin_waitforendscript
            # because that can get called multiple times and we don't want
            # bodydata to get reset other than the first time.
            self.begin_bodydata(None)
            return "waitforendscript"
        return "bodydata"

    def dataReceived(self, data):
        stateTable = self._buildStateTable()
        if not self.state:
            # all UTF-16 starts with this string
            if data.startswith((b"\xff\xfe", b"\xfe\xff")):
                self._prepend = data[0:2]
                self.encodings.append("UTF-16")
                data = data[2:]
            self.state = "begin"
        if self.encodings:
            data = self._decode(data)
        else:
            data = data.decode("utf-8")
        # bring state, lineno, colno into local scope
        lineno, colno = self.lineno, self.colno
        curState = self.state
        # replace saveMark with a nested scope function
        _saveMark = self.saveMark

        def saveMark():
            return (lineno, colno)

        self.saveMark = saveMark
        # fetch functions from the stateTable
        beginFn, doFn, endFn = stateTable[curState]
        try:
            for byte in data:
                # do newline stuff
                if byte == "\n":
                    lineno += 1
                    colno = 0
                else:
                    colno += 1
                newState = doFn(byte)
                if newState is not None and newState != curState:
                    # this is the endFn from the previous state
                    endFn()
                    curState = newState
                    beginFn, doFn, endFn = stateTable[curState]
                    beginFn(byte)
        finally:
            self.saveMark = _saveMark
            self.lineno, self.colno = lineno, colno
        # state doesn't make sense if there's an exception..
        self.state = curState

    def connectionLost(self, reason):
        """
        End the last state we were in.
        """
        stateTable = self._buildStateTable()
        stateTable[self.state][END_HANDLER]()

    # state methods

    def do_begin(self, byte):
        if byte.isspace():
            return
        if byte != "<":
            if self.beExtremelyLenient:
                self._leadingBodyData = byte
                return "bodydata"
            self._parseError(f"First char of document [{byte!r}] wasn't <")
        return "tagstart"

    def begin_comment(self, byte):
        self.commentbuf = ""

    def do_comment(self, byte):
        self.commentbuf += byte
        if self.commentbuf.endswith("-->"):
            self.gotComment(self.commentbuf[:-3])
            return "bodydata"

    def begin_tagstart(self, byte):
        self.tagName = ""  # name of the tag
        self.tagAttributes = {}  # attributes of the tag
        self.termtag = 0  # is the tag self-terminating
        self.endtag = 0

    def do_tagstart(self, byte):
        if byte.isalnum() or byte in identChars:
            self.tagName += byte
            if self.tagName == "!--":
                return "comment"
        elif byte.isspace():
            if self.tagName:
                if self.endtag:
                    # properly strict thing to do here is probably to only
                    # accept whitespace
                    return "waitforgt"
                return "attrs"
            else:
                self._parseError("Whitespace before tag-name")
        elif byte == ">":
            if self.endtag:
                self.gotTagEnd(self.tagName)
                return "bodydata"
            else:
                self.gotTagStart(self.tagName, {})
                return (
                    (not self.beExtremelyLenient) and "bodydata" or self.maybeBodyData()
                )
        elif byte == "/":
            if self.tagName:
                return "afterslash"
            else:
                self.endtag = 1
        elif byte in "!?":
            if self.tagName:
                if not self.beExtremelyLenient:
                    self._parseError("Invalid character in tag-name")
            else:
                self.tagName += byte
                self.termtag = 1
        elif byte == "[":
            if self.tagName == "!":
                return "expectcdata"
            else:
                self._parseError("Invalid '[' in tag-name")
        else:
            if self.beExtremelyLenient:
                self.bodydata = "<"
                return "unentity"
            self._parseError("Invalid tag character: %r" % byte)

    def begin_unentity(self, byte):
        self.bodydata += byte

    def do_unentity(self, byte):
        self.bodydata += byte
        return "bodydata"

    def end_unentity(self):
        self.gotText(self.bodydata)

    def begin_expectcdata(self, byte):
        self.cdatabuf = byte

    def do_expectcdata(self, byte):
        self.cdatabuf += byte
        cdb = self.cdatabuf
        cd = "[CDATA["
        if len(cd) > len(cdb):
            if cd.startswith(cdb):
                return
            elif self.beExtremelyLenient:
                ## WHAT THE CRAP!?  MSWord9 generates HTML that includes these
                ## bizarre <![if !foo]> <![endif]> chunks, so I've gotta ignore
                ## 'em as best I can.  this should really be a separate parse
                ## state but I don't even have any idea what these _are_.
                return "waitforgt"
            else:
                self._parseError("Mal-formed CDATA header")
        if cd == cdb:
            self.cdatabuf = ""
            return "cdata"
        self._parseError("Mal-formed CDATA header")

    def do_cdata(self, byte):
        self.cdatabuf += byte
        if self.cdatabuf.endswith("]]>"):
            self.cdatabuf = self.cdatabuf[:-3]
            return "bodydata"

    def end_cdata(self):
        self.gotCData(self.cdatabuf)
        self.cdatabuf = ""

    def do_attrs(self, byte):
        if byte.isalnum() or byte in identChars:
            # XXX FIXME really handle !DOCTYPE at some point
            if self.tagName == "!DOCTYPE":
                return "doctype"
            if self.tagName[0] in "!?":
                return "waitforgt"
            return "attrname"
        elif byte.isspace():
            return
        elif byte == ">":
            self.gotTagStart(self.tagName, self.tagAttributes)
            return (not self.beExtremelyLenient) and "bodydata" or self.maybeBodyData()
        elif byte == "/":
            return "afterslash"
        elif self.beExtremelyLenient:
            # discard and move on?  Only case I've seen of this so far was:
            # <foo bar="baz"">
            return
        self._parseError("Unexpected character: %r" % byte)

    def begin_doctype(self, byte):
        self.doctype = byte

    def do_doctype(self, byte):
        if byte == ">":
            return "bodydata"
        self.doctype += byte

    def end_doctype(self):
        self.gotDoctype(self.doctype)
        self.doctype = None

    def do_waitforgt(self, byte):
        if byte == ">":
            if self.endtag or not self.beExtremelyLenient:
                return "bodydata"
            return self.maybeBodyData()

    def begin_attrname(self, byte):
        self.attrname = byte
        self._attrname_termtag = 0

    def do_attrname(self, byte):
        if byte.isalnum() or byte in identChars:
            self.attrname += byte
            return
        elif byte == "=":
            return "beforeattrval"
        elif byte.isspace():
            return "beforeeq"
        elif self.beExtremelyLenient:
            if byte in "\"'":
                return "attrval"
            if byte in lenientIdentChars or byte.isalnum():
                self.attrname += byte
                return
            if byte == "/":
                self._attrname_termtag = 1
                return
            if byte == ">":
                self.attrval = "True"
                self.tagAttributes[self.attrname] = self.attrval
                self.gotTagStart(self.tagName, self.tagAttributes)
                if self._attrname_termtag:
                    self.gotTagEnd(self.tagName)
                    return "bodydata"
                return self.maybeBodyData()
            # something is really broken. let's leave this attribute where it
            # is and move on to the next thing
            return
        self._parseError(f"Invalid attribute name: {self.attrname!r} {byte!r}")

    def do_beforeattrval(self, byte):
        if byte in "\"'":
            return "attrval"
        elif byte.isspace():
            return
        elif self.beExtremelyLenient:
            if byte in lenientIdentChars or byte.isalnum():
                return "messyattr"
            if byte == ">":
                self.attrval = "True"
                self.tagAttributes[self.attrname] = self.attrval
                self.gotTagStart(self.tagName, self.tagAttributes)
                return self.maybeBodyData()
            if byte == "\\":
                # I saw this in actual HTML once:
                # <font size=\"3\"><sup>SM</sup></font>
                return
        self._parseError(
            "Invalid initial attribute value: %r; Attribute values must be quoted."
            % byte
        )

    attrname = ""
    attrval = ""

    def begin_beforeeq(self, byte):
        self._beforeeq_termtag = 0

    def do_beforeeq(self, byte):
        if byte == "=":
            return "beforeattrval"
        elif byte.isspace():
            return
        elif self.beExtremelyLenient:
            if byte.isalnum() or byte in identChars:
                self.attrval = "True"
                self.tagAttributes[self.attrname] = self.attrval
                return "attrname"
            elif byte == ">":
                self.attrval = "True"
                self.tagAttributes[self.attrname] = self.attrval
                self.gotTagStart(self.tagName, self.tagAttributes)
                if self._beforeeq_termtag:
                    self.gotTagEnd(self.tagName)
                    return "bodydata"
                return self.maybeBodyData()
            elif byte == "/":
                self._beforeeq_termtag = 1
                return
        self._parseError("Invalid attribute")

    def begin_attrval(self, byte):
        self.quotetype = byte
        self.attrval = ""

    def do_attrval(self, byte):
        if byte == self.quotetype:
            return "attrs"
        self.attrval += byte

    def end_attrval(self):
        self.tagAttributes[self.attrname] = self.attrval
        self.attrname = self.attrval = ""

    def begin_messyattr(self, byte):
        self.attrval = byte

    def do_messyattr(self, byte):
        if byte.isspace():
            return "attrs"
        elif byte == ">":
            endTag = 0
            if self.attrval.endswith("/"):
                endTag = 1
                self.attrval = self.attrval[:-1]
            self.tagAttributes[self.attrname] = self.attrval
            self.gotTagStart(self.tagName, self.tagAttributes)
            if endTag:
                self.gotTagEnd(self.tagName)
                return "bodydata"
            return self.maybeBodyData()
        else:
            self.attrval += byte

    def end_messyattr(self):
        if self.attrval:
            self.tagAttributes[self.attrname] = self.attrval

    def begin_afterslash(self, byte):
        self._after_slash_closed = 0

    def do_afterslash(self, byte):
        # this state is only after a self-terminating slash, e.g. <foo/>
        if self._after_slash_closed:
            self._parseError("Mal-formed")  # XXX When does this happen??
        if byte != ">":
            if self.beExtremelyLenient:
                return
            else:
                self._parseError("No data allowed after '/'")
        self._after_slash_closed = 1
        self.gotTagStart(self.tagName, self.tagAttributes)
        self.gotTagEnd(self.tagName)
        # don't need maybeBodyData here because there better not be
        # any javascript code after a <script/>... we'll see :(
        return "bodydata"

    def begin_bodydata(self, byte):
        if self._leadingBodyData:
            self.bodydata = self._leadingBodyData
            del self._leadingBodyData
        else:
            self.bodydata = ""

    def do_bodydata(self, byte):
        if byte == "<":
            return "tagstart"
        if byte == "&":
            return "entityref"
        self.bodydata += byte

    def end_bodydata(self):
        self.gotText(self.bodydata)
        self.bodydata = ""

    def do_waitforendscript(self, byte):
        if byte == "<":
            return "waitscriptendtag"
        self.bodydata += byte

    def begin_waitscriptendtag(self, byte):
        self.temptagdata = ""
        self.tagName = ""
        self.endtag = 0

    def do_waitscriptendtag(self, byte):
        # 1 enforce / as first byte read
        # 2 enforce following bytes to be subset of "script" until
        #   tagName == "script"
        #   2a when that happens, gotText(self.bodydata) and gotTagEnd(self.tagName)
        # 3 spaces can happen anywhere, they're ignored
        #   e.g. < / script >
        # 4 anything else causes all data I've read to be moved to the
        #   bodydata, and switch back to waitforendscript state

        # If it turns out this _isn't_ a </script>, we need to
        # remember all the data we've been through so we can append it
        # to bodydata
        self.temptagdata += byte

        # 1
        if byte == "/":
            self.endtag = True
        elif not self.endtag:
            self.bodydata += "<" + self.temptagdata
            return "waitforendscript"
        # 2
        elif byte.isalnum() or byte in identChars:
            self.tagName += byte
            if not "script".startswith(self.tagName):
                self.bodydata += "<" + self.temptagdata
                return "waitforendscript"
            elif self.tagName == "script":
                self.gotText(self.bodydata)
                self.gotTagEnd(self.tagName)
                return "waitforgt"
        # 3
        elif byte.isspace():
            return "waitscriptendtag"
        # 4
        else:
            self.bodydata += "<" + self.temptagdata
            return "waitforendscript"

    def begin_entityref(self, byte):
        self.erefbuf = ""
        self.erefextra = ""  # extra bit for lenient mode

    def do_entityref(self, byte):
        if byte.isspace() or byte == "<":
            if self.beExtremelyLenient:
                # '&foo' probably was '&amp;foo'
                if self.erefbuf and self.erefbuf != "amp":
                    self.erefextra = self.erefbuf
                self.erefbuf = "amp"
                if byte == "<":
                    return "tagstart"
                else:
                    self.erefextra += byte
                    return "spacebodydata"
            self._parseError("Bad entity reference")
        elif byte != ";":
            self.erefbuf += byte
        else:
            return "bodydata"

    def end_entityref(self):
        self.gotEntityReference(self.erefbuf)

    # hacky support for space after & in entityref in beExtremelyLenient
    # state should only happen in that case
    def begin_spacebodydata(self, byte):
        self.bodydata = self.erefextra
        self.erefextra = None

    do_spacebodydata = do_bodydata
    end_spacebodydata = end_bodydata

    # Sorta SAX-ish API

    def gotTagStart(self, name, attributes):
        """Encountered an opening tag.

        Default behaviour is to print."""
        print("begin", name, attributes)

    def gotText(self, data):
        """Encountered text

        Default behaviour is to print."""
        print("text:", repr(data))

    def gotEntityReference(self, entityRef):
        """Encountered mnemonic entity reference

        Default behaviour is to print."""
        print("entityRef: &%s;" % entityRef)

    def gotComment(self, comment):
        """Encountered comment.

        Default behaviour is to ignore."""
        pass

    def gotCData(self, cdata):
        """Encountered CDATA

        Default behaviour is to call the gotText method"""
        self.gotText(cdata)

    def gotDoctype(self, doctype):
        """Encountered DOCTYPE

        This is really grotty: it basically just gives you everything between
        '<!DOCTYPE' and '>' as an argument.
        """
        print("!DOCTYPE", repr(doctype))

    def gotTagEnd(self, name):
        """Encountered closing tag

        Default behaviour is to print."""
        print("end", name)
