# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Dict client protocol implementation.

@author: Pavel Pergamenshchik
"""

from twisted.protocols import basic
from twisted.internet import defer, protocol
from twisted.python import log
from io import BytesIO

def parseParam(line):
    """Chew one dqstring or atom from beginning of line and return (param, remaningline)"""
    if line == b'':
        return (None, b'')
    elif line[0:1] != b'"': # atom
        mode = 1
    else: # dqstring
        mode = 2
    res = b""
    io = BytesIO(line)
    if mode == 2: # skip the opening quote
        io.read(1)
    while 1:
        a = io.read(1)
        if a == b'"':
            if mode == 2:
                io.read(1) # skip the separating space
                return (res, io.read())
        elif a == b'\\':
            a = io.read(1)
            if a == b'':
                return (None, line) # unexpected end of string
        elif a == b'':
            if mode == 1:
                return (res, io.read())
            else:
                return (None, line) # unexpected end of string
        elif a == b' ':
            if mode == 1:
                return (res, io.read())
        res += a



def makeAtom(line):
    """Munch a string into an 'atom'"""
    # FIXME: proper quoting
    return filter(lambda x: not (x in map(chr, range(33)+[34, 39, 92])), line)



def makeWord(s):
    mustquote = range(33)+[34, 39, 92]
    result = []
    for c in s:
        if ord(c) in mustquote:
            result.append(b"\\")
        result.append(c)
    s = b"".join(result)
    return s



def parseText(line):
    if len(line) == 1 and line == b'.':
        return None
    else:
        if len(line) > 1 and line[0:2] == b'..':
            line = line[1:]
        return line



class Definition:
    """A word definition"""
    def __init__(self, name, db, dbdesc, text):
        self.name = name
        self.db = db
        self.dbdesc = dbdesc
        self.text = text # list of strings not terminated by newline



class DictClient(basic.LineReceiver):
    """dict (RFC2229) client"""

    data = None # multiline data
    MAX_LENGTH = 1024
    state = None
    mode = None
    result = None
    factory = None

    def __init__(self):
        self.data = None
        self.result = None


    def connectionMade(self):
        self.state = "conn"
        self.mode = "command"


    def sendLine(self, line):
        """Throw up if the line is longer than 1022 characters"""
        if len(line) > self.MAX_LENGTH - 2:
            raise ValueError("DictClient tried to send a too long line")
        basic.LineReceiver.sendLine(self, line)


    def lineReceived(self, line):
        try:
            line = line.decode("utf-8")
        except UnicodeError: # garbage received, skip
            return
        if self.mode == "text": # we are receiving textual data
            code = "text"
        else:
            if len(line) < 4:
                log.msg("DictClient got invalid line from server -- %s" % line)
                self.protocolError("Invalid line from server")
                self.transport.LoseConnection()
                return
            code = int(line[:3])
            line = line[4:]
        method = getattr(self, 'dictCode_%s_%s' % (code, self.state), self.dictCode_default)
        method(line)


    def dictCode_default(self, line):
        """Unknown message"""
        log.msg("DictClient got unexpected message from server -- %s" % line)
        self.protocolError("Unexpected server message")
        self.transport.loseConnection()


    def dictCode_221_ready(self, line):
        """We are about to get kicked off, do nothing"""
        pass


    def dictCode_220_conn(self, line):
        """Greeting message"""
        self.state = "ready"
        self.dictConnected()


    def dictCode_530_conn(self):
        self.protocolError("Access denied")
        self.transport.loseConnection()


    def dictCode_420_conn(self):
        self.protocolError("Server temporarily unavailable")
        self.transport.loseConnection()


    def dictCode_421_conn(self):
        self.protocolError("Server shutting down at operator request")
        self.transport.loseConnection()


    def sendDefine(self, database, word):
        """Send a dict DEFINE command"""
        assert self.state == "ready", "DictClient.sendDefine called when not in ready state"
        self.result = None  # these two are just in case. In "ready" state, result and data
        self.data = None    # should be None
        self.state = "define"
        command = "DEFINE %s %s" % (makeAtom(database.encode("UTF-8")), makeWord(word.encode("UTF-8")))
        self.sendLine(command)


    def sendMatch(self, database, strategy, word):
        """Send a dict MATCH command"""
        assert self.state == "ready", "DictClient.sendMatch called when not in ready state"
        self.result = None
        self.data = None
        self.state = "match"
        command = "MATCH %s %s %s" % (makeAtom(database), makeAtom(strategy), makeAtom(word))
        self.sendLine(command.encode("UTF-8"))

    def dictCode_550_define(self, line):
        """Invalid database"""
        self.mode = "ready"
        self.defineFailed("Invalid database")


    def dictCode_550_match(self, line):
        """Invalid database"""
        self.mode = "ready"
        self.matchFailed("Invalid database")


    def dictCode_551_match(self, line):
        """Invalid strategy"""
        self.mode = "ready"
        self.matchFailed("Invalid strategy")


    def dictCode_552_define(self, line):
        """No match"""
        self.mode = "ready"
        self.defineFailed("No match")


    def dictCode_552_match(self, line):
        """No match"""
        self.mode = "ready"
        self.matchFailed("No match")


    def dictCode_150_define(self, line):
        """n definitions retrieved"""
        self.result = []


    def dictCode_151_define(self, line):
        """Definition text follows"""
        self.mode = "text"
        (word, line) = parseParam(line)
        (db, line) = parseParam(line)
        (dbdesc, line) = parseParam(line)
        if not (word and db and dbdesc):
            self.protocolError("Invalid server response")
            self.transport.loseConnection()
        else:
            self.result.append(Definition(word, db, dbdesc, []))
            self.data = []


    def dictCode_152_match(self, line):
        """n matches found, text follows"""
        self.mode = "text"
        self.result = []
        self.data = []


    def dictCode_text_define(self, line):
        """A line of definition text received"""
        res = parseText(line)
        if res == None:
            self.mode = "command"
            self.result[-1].text = self.data
            self.data = None
        else:
            self.data.append(line)


    def dictCode_text_match(self, line):
        """One line of match text received"""
        def l(s):
            p1, t = parseParam(s)
            p2, t = parseParam(t)
            return (p1, p2)
        res = parseText(line)
        if res == None:
            self.mode = "command"
            self.result = map(l, self.data)
            self.data = None
        else:
            self.data.append(line)


    def dictCode_250_define(self, line):
        """ok"""
        t = self.result
        self.result = None
        self.state = "ready"
        self.defineDone(t)


    def dictCode_250_match(self, line):
        """ok"""
        t = self.result
        self.result = None
        self.state = "ready"
        self.matchDone(t)


    def protocolError(self, reason):
        """override to catch unexpected dict protocol conditions"""
        pass


    def dictConnected(self):
        """override to be notified when the server is ready to accept commands"""
        pass


    def defineFailed(self, reason):
        """override to catch reasonable failure responses to DEFINE"""
        pass


    def defineDone(self, result):
        """override to catch successful DEFINE"""
        pass


    def matchFailed(self, reason):
        """override to catch resonable failure responses to MATCH"""
        pass


    def matchDone(self, result):
        """override to catch successful MATCH"""
        pass



class InvalidResponse(Exception):
    pass



class DictLookup(DictClient):
    """Utility class for a single dict transaction. To be used with DictLookupFactory"""

    def protocolError(self, reason):
        if not self.factory.done:
            self.factory.d.errback(InvalidResponse(reason))
            self.factory.clientDone()


    def dictConnected(self):
        if self.factory.queryType == "define":
            apply(self.sendDefine, self.factory.param)
        elif self.factory.queryType == "match":
            apply(self.sendMatch, self.factory.param)


    def defineFailed(self, reason):
        self.factory.d.callback([])
        self.factory.clientDone()
        self.transport.loseConnection()


    def defineDone(self, result):
        self.factory.d.callback(result)
        self.factory.clientDone()
        self.transport.loseConnection()


    def matchFailed(self, reason):
        self.factory.d.callback([])
        self.factory.clientDone()
        self.transport.loseConnection()


    def matchDone(self, result):
        self.factory.d.callback(result)
        self.factory.clientDone()
        self.transport.loseConnection()



class DictLookupFactory(protocol.ClientFactory):
    """Utility factory for a single dict transaction"""
    protocol = DictLookup
    done = None

    def __init__(self, queryType, param, d):
        self.queryType = queryType
        self.param = param
        self.d = d
        self.done = 0


    def clientDone(self):
        """Called by client when done."""
        self.done = 1
        del self.d


    def clientConnectionFailed(self, connector, error):
        self.d.errback(error)


    def clientConnectionLost(self, connector, error):
        if not self.done:
            self.d.errback(error)


    def buildProtocol(self, addr):
        p = self.protocol()
        p.factory = self
        return p



def define(host, port, database, word):
    """Look up a word using a dict server"""
    d = defer.Deferred()
    factory = DictLookupFactory("define", (database, word), d)

    from twisted.internet import reactor
    reactor.connectTCP(host, port, factory)
    return d



def match(host, port, database, strategy, word):
    """Match a word using a dict server"""
    d = defer.Deferred()
    factory = DictLookupFactory("match", (database, strategy, word), d)

    from twisted.internet import reactor
    reactor.connectTCP(host, port, factory)
    return d

