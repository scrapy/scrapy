# -*- test-case-name: twisted.mail.test.test_mailmail -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Implementation module for the I{mailmail} command.
"""


import email.utils
import getpass
import os
import sys
from configparser import ConfigParser
from io import StringIO

from twisted.copyright import version
from twisted.internet import reactor
from twisted.logger import Logger, textFileLogObserver
from twisted.mail import smtp

GLOBAL_CFG = "/etc/mailmail"
LOCAL_CFG = os.path.expanduser("~/.twisted/mailmail")
SMARTHOST = "127.0.0.1"

ERROR_FMT = """\
Subject: Failed Message Delivery

  Message delivery failed.  The following occurred:

  %s
--
The Twisted sendmail application.
"""

_logObserver = textFileLogObserver(sys.stderr)
_log = Logger(observer=_logObserver)


class Options:
    """
    Store the values of the parsed command-line options to the I{mailmail}
    script.

    @type to: L{list} of L{str}
    @ivar to: The addresses to which to deliver this message.

    @type sender: L{str}
    @ivar sender: The address from which this message is being sent.

    @type body: C{file}
    @ivar body: The object from which the message is to be read.
    """


def getlogin():
    try:
        return os.getlogin()
    except BaseException:
        return getpass.getuser()


_unsupportedOption = SystemExit("Unsupported option.")


def parseOptions(argv):
    o = Options()
    o.to = [e for e in argv if not e.startswith("-")]
    o.sender = getlogin()

    # Just be very stupid

    # Skip -bm -- it is the default

    # Add a non-standard option for querying the version of this tool.
    if "--version" in argv:
        print("mailmail version:", version)
        raise SystemExit()

    # -bp lists queue information.  Screw that.
    if "-bp" in argv:
        raise _unsupportedOption

    # -bs makes sendmail use stdin/stdout as its transport.  Screw that.
    if "-bs" in argv:
        raise _unsupportedOption

    # -F sets who the mail is from, but is overridable by the From header
    if "-F" in argv:
        o.sender = argv[argv.index("-F") + 1]
        o.to.remove(o.sender)

    # -i and -oi makes us ignore lone "."
    if ("-i" in argv) or ("-oi" in argv):
        raise _unsupportedOption

    # -odb is background delivery
    if "-odb" in argv:
        o.background = True
    else:
        o.background = False

    # -odf is foreground delivery
    if "-odf" in argv:
        o.background = False
    else:
        o.background = True

    # -oem and -em cause errors to be mailed back to the sender.
    # It is also the default.

    # -oep and -ep cause errors to be printed to stderr
    if ("-oep" in argv) or ("-ep" in argv):
        o.printErrors = True
    else:
        o.printErrors = False

    # -om causes a copy of the message to be sent to the sender if the sender
    # appears in an alias expansion.  We do not support aliases.
    if "-om" in argv:
        raise _unsupportedOption

    # -t causes us to pick the recipients of the message from
    # the To, Cc, and Bcc headers, and to remove the Bcc header
    # if present.
    if "-t" in argv:
        o.recipientsFromHeaders = True
        o.excludeAddresses = o.to
        o.to = []
    else:
        o.recipientsFromHeaders = False
        o.exludeAddresses = []

    requiredHeaders = {
        "from": [],
        "to": [],
        "cc": [],
        "bcc": [],
        "date": [],
    }

    buffer = StringIO()
    while 1:
        write = 1
        line = sys.stdin.readline()
        if not line.strip():
            break

        hdrs = line.split(": ", 1)

        hdr = hdrs[0].lower()
        if o.recipientsFromHeaders and hdr in ("to", "cc", "bcc"):
            o.to.extend([email.utils.parseaddr(hdrs[1])[1]])
            if hdr == "bcc":
                write = 0
        elif hdr == "from":
            o.sender = email.utils.parseaddr(hdrs[1])[1]

        if hdr in requiredHeaders:
            requiredHeaders[hdr].append(hdrs[1])

        if write:
            buffer.write(line)

    if not requiredHeaders["from"]:
        buffer.write(f"From: {o.sender}\r\n")
    if not requiredHeaders["to"]:
        if not o.to:
            raise SystemExit("No recipients specified.")
        buffer.write("To: {}\r\n".format(", ".join(o.to)))
    if not requiredHeaders["date"]:
        buffer.write(f"Date: {smtp.rfc822date()}\r\n")

    buffer.write(line)

    if o.recipientsFromHeaders:
        for a in o.excludeAddresses:
            try:
                o.to.remove(a)
            except BaseException:
                pass

    buffer.seek(0, 0)
    o.body = StringIO(buffer.getvalue() + sys.stdin.read())
    return o


class Configuration:
    """

    @ivar allowUIDs: A list of UIDs which are allowed to send mail.
    @ivar allowGIDs: A list of GIDs which are allowed to send mail.
    @ivar denyUIDs: A list of UIDs which are not allowed to send mail.
    @ivar denyGIDs: A list of GIDs which are not allowed to send mail.

    @type defaultAccess: L{bool}
    @ivar defaultAccess: L{True} if access will be allowed when no other access
    control rule matches or L{False} if it will be denied in that case.

    @ivar useraccess: Either C{'allow'} to check C{allowUID} first
    or C{'deny'} to check C{denyUID} first.

    @ivar groupaccess: Either C{'allow'} to check C{allowGID} first or
    C{'deny'} to check C{denyGID} first.

    @ivar identities: A L{dict} mapping hostnames to credentials to use when
    sending mail to that host.

    @ivar smarthost: L{None} or a hostname through which all outgoing mail will
    be sent.

    @ivar domain: L{None} or the hostname with which to identify ourselves when
    connecting to an MTA.
    """

    def __init__(self):
        self.allowUIDs = []
        self.denyUIDs = []
        self.allowGIDs = []
        self.denyGIDs = []
        self.useraccess = "deny"
        self.groupaccess = "deny"

        self.identities = {}
        self.smarthost = None
        self.domain = None

        self.defaultAccess = True


def loadConfig(path):
    # [useraccess]
    # allow=uid1,uid2,...
    # deny=uid1,uid2,...
    # order=allow,deny
    # [groupaccess]
    # allow=gid1,gid2,...
    # deny=gid1,gid2,...
    # order=deny,allow
    # [identity]
    # host1=username:password
    # host2=username:password
    # [addresses]
    # smarthost=a.b.c.d
    # default_domain=x.y.z

    c = Configuration()

    if not os.access(path, os.R_OK):
        return c

    p = ConfigParser()
    p.read(path)

    au = c.allowUIDs
    du = c.denyUIDs
    ag = c.allowGIDs
    dg = c.denyGIDs
    for (section, a, d) in (("useraccess", au, du), ("groupaccess", ag, dg)):
        if p.has_section(section):
            for (mode, L) in (("allow", a), ("deny", d)):
                if p.has_option(section, mode) and p.get(section, mode):
                    for sectionID in p.get(section, mode).split(","):
                        try:
                            sectionID = int(sectionID)
                        except ValueError:
                            _log.error(
                                "Illegal {prefix}ID in "
                                "[{section}] section: {sectionID}",
                                prefix=section[0].upper(),
                                section=section,
                                sectionID=sectionID,
                            )
                        else:
                            L.append(sectionID)
            order = p.get(section, "order")
            order = [s.split() for s in [s.lower() for s in order.split(",")]]
            if order[0] == "allow":
                setattr(c, section, "allow")
            else:
                setattr(c, section, "deny")

    if p.has_section("identity"):
        for (host, up) in p.items("identity"):
            parts = up.split(":", 1)
            if len(parts) != 2:
                _log.error("Illegal entry in [identity] section: {section}", section=up)
                continue
            c.identities[host] = parts

    if p.has_section("addresses"):
        if p.has_option("addresses", "smarthost"):
            c.smarthost = p.get("addresses", "smarthost")
        if p.has_option("addresses", "default_domain"):
            c.domain = p.get("addresses", "default_domain")

    return c


def success(result):
    reactor.stop()


failed = None


def failure(f):
    global failed
    reactor.stop()
    failed = f


def sendmail(host, options, ident):
    d = smtp.sendmail(host, options.sender, options.to, options.body)
    d.addCallbacks(success, failure)
    reactor.run()


def senderror(failure, options):
    recipient = [options.sender]
    sender = '"Internally Generated Message ({})"<postmaster@{}>'.format(
        sys.argv[0], smtp.DNSNAME.decode("ascii")
    )
    error = StringIO()
    failure.printTraceback(file=error)
    body = StringIO(ERROR_FMT % error.getvalue())
    d = smtp.sendmail("localhost", sender, recipient, body)
    d.addBoth(lambda _: reactor.stop())


def deny(conf):
    uid = os.getuid()
    gid = os.getgid()

    if conf.useraccess == "deny":
        if uid in conf.denyUIDs:
            return True
        if uid in conf.allowUIDs:
            return False
    else:
        if uid in conf.allowUIDs:
            return False
        if uid in conf.denyUIDs:
            return True

    if conf.groupaccess == "deny":
        if gid in conf.denyGIDs:
            return True
        if gid in conf.allowGIDs:
            return False
    else:
        if gid in conf.allowGIDs:
            return False
        if gid in conf.denyGIDs:
            return True

    return not conf.defaultAccess


def run():
    o = parseOptions(sys.argv[1:])
    gConf = loadConfig(GLOBAL_CFG)
    lConf = loadConfig(LOCAL_CFG)

    if deny(gConf) or deny(lConf):
        _log.error("Permission denied")
        return

    host = lConf.smarthost or gConf.smarthost or SMARTHOST

    ident = gConf.identities.copy()
    ident.update(lConf.identities)

    if lConf.domain:
        smtp.DNSNAME = lConf.domain
    elif gConf.domain:
        smtp.DNSNAME = gConf.domain

    sendmail(host, o, ident)

    if failed:
        if o.printErrors:
            failed.printTraceback(file=sys.stderr)
            raise SystemExit(1)
        else:
            senderror(failed, o)
