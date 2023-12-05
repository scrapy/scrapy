# -*- test-case-name: twisted.conch.test.test_knownhosts -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
An implementation of the OpenSSH known_hosts database.

@since: 8.2
"""


import hmac
import sys
from binascii import Error as DecodeError, a2b_base64, b2a_base64
from contextlib import closing
from hashlib import sha1

from zope.interface import implementer

from twisted.conch.error import HostKeyChanged, InvalidEntry, UserRejectedKey
from twisted.conch.interfaces import IKnownHostEntry
from twisted.conch.ssh.keys import BadKeyError, FingerprintFormats, Key
from twisted.internet import defer
from twisted.logger import Logger
from twisted.python.compat import nativeString
from twisted.python.randbytes import secureRandom
from twisted.python.util import FancyEqMixin

log = Logger()


def _b64encode(s):
    """
    Encode a binary string as base64 with no trailing newline.

    @param s: The string to encode.
    @type s: L{bytes}

    @return: The base64-encoded string.
    @rtype: L{bytes}
    """
    return b2a_base64(s).strip()


def _extractCommon(string):
    """
    Extract common elements of base64 keys from an entry in a hosts file.

    @param string: A known hosts file entry (a single line).
    @type string: L{bytes}

    @return: a 4-tuple of hostname data (L{bytes}), ssh key type (L{bytes}), key
        (L{Key}), and comment (L{bytes} or L{None}).  The hostname data is
        simply the beginning of the line up to the first occurrence of
        whitespace.
    @rtype: L{tuple}
    """
    elements = string.split(None, 2)
    if len(elements) != 3:
        raise InvalidEntry()
    hostnames, keyType, keyAndComment = elements
    splitkey = keyAndComment.split(None, 1)
    if len(splitkey) == 2:
        keyString, comment = splitkey
        comment = comment.rstrip(b"\n")
    else:
        keyString = splitkey[0]
        comment = None
    key = Key.fromString(a2b_base64(keyString))
    return hostnames, keyType, key, comment


class _BaseEntry:
    """
    Abstract base of both hashed and non-hashed entry objects, since they
    represent keys and key types the same way.

    @ivar keyType: The type of the key; either ssh-dss or ssh-rsa.
    @type keyType: L{bytes}

    @ivar publicKey: The server public key indicated by this line.
    @type publicKey: L{twisted.conch.ssh.keys.Key}

    @ivar comment: Trailing garbage after the key line.
    @type comment: L{bytes}
    """

    def __init__(self, keyType, publicKey, comment):
        self.keyType = keyType
        self.publicKey = publicKey
        self.comment = comment

    def matchesKey(self, keyObject):
        """
        Check to see if this entry matches a given key object.

        @param keyObject: A public key object to check.
        @type keyObject: L{Key}

        @return: C{True} if this entry's key matches C{keyObject}, C{False}
            otherwise.
        @rtype: L{bool}
        """
        return self.publicKey == keyObject


@implementer(IKnownHostEntry)
class PlainEntry(_BaseEntry):
    """
    A L{PlainEntry} is a representation of a plain-text entry in a known_hosts
    file.

    @ivar _hostnames: the list of all host-names associated with this entry.
    @type _hostnames: L{list} of L{bytes}
    """

    def __init__(self, hostnames, keyType, publicKey, comment):
        self._hostnames = hostnames
        super().__init__(keyType, publicKey, comment)

    @classmethod
    def fromString(cls, string):
        """
        Parse a plain-text entry in a known_hosts file, and return a
        corresponding L{PlainEntry}.

        @param string: a space-separated string formatted like "hostname
        key-type base64-key-data comment".

        @type string: L{bytes}

        @raise DecodeError: if the key is not valid encoded as valid base64.

        @raise InvalidEntry: if the entry does not have the right number of
        elements and is therefore invalid.

        @raise BadKeyError: if the key, once decoded from base64, is not
        actually an SSH key.

        @return: an IKnownHostEntry representing the hostname and key in the
        input line.

        @rtype: L{PlainEntry}
        """
        hostnames, keyType, key, comment = _extractCommon(string)
        self = cls(hostnames.split(b","), keyType, key, comment)
        return self

    def matchesHost(self, hostname):
        """
        Check to see if this entry matches a given hostname.

        @param hostname: A hostname or IP address literal to check against this
            entry.
        @type hostname: L{bytes}

        @return: C{True} if this entry is for the given hostname or IP address,
            C{False} otherwise.
        @rtype: L{bool}
        """
        if isinstance(hostname, str):
            hostname = hostname.encode("utf-8")
        return hostname in self._hostnames

    def toString(self):
        """
        Implement L{IKnownHostEntry.toString} by recording the comma-separated
        hostnames, key type, and base-64 encoded key.

        @return: The string representation of this entry, with unhashed hostname
            information.
        @rtype: L{bytes}
        """
        fields = [
            b",".join(self._hostnames),
            self.keyType,
            _b64encode(self.publicKey.blob()),
        ]
        if self.comment is not None:
            fields.append(self.comment)
        return b" ".join(fields)


@implementer(IKnownHostEntry)
class UnparsedEntry:
    """
    L{UnparsedEntry} is an entry in a L{KnownHostsFile} which can't actually be
    parsed; therefore it matches no keys and no hosts.
    """

    def __init__(self, string):
        """
        Create an unparsed entry from a line in a known_hosts file which cannot
        otherwise be parsed.
        """
        self._string = string

    def matchesHost(self, hostname):
        """
        Always returns False.
        """
        return False

    def matchesKey(self, key):
        """
        Always returns False.
        """
        return False

    def toString(self):
        """
        Returns the input line, without its newline if one was given.

        @return: The string representation of this entry, almost exactly as was
            used to initialize this entry but without a trailing newline.
        @rtype: L{bytes}
        """
        return self._string.rstrip(b"\n")


def _hmacedString(key, string):
    """
    Return the SHA-1 HMAC hash of the given key and string.

    @param key: The HMAC key.
    @type key: L{bytes}

    @param string: The string to be hashed.
    @type string: L{bytes}

    @return: The keyed hash value.
    @rtype: L{bytes}
    """
    hash = hmac.HMAC(key, digestmod=sha1)
    if isinstance(string, str):
        string = string.encode("utf-8")
    hash.update(string)
    return hash.digest()


@implementer(IKnownHostEntry)
class HashedEntry(_BaseEntry, FancyEqMixin):
    """
    A L{HashedEntry} is a representation of an entry in a known_hosts file
    where the hostname has been hashed and salted.

    @ivar _hostSalt: the salt to combine with a hostname for hashing.

    @ivar _hostHash: the hashed representation of the hostname.

    @cvar MAGIC: the 'hash magic' string used to identify a hashed line in a
    known_hosts file as opposed to a plaintext one.
    """

    MAGIC = b"|1|"

    compareAttributes = ("_hostSalt", "_hostHash", "keyType", "publicKey", "comment")

    def __init__(self, hostSalt, hostHash, keyType, publicKey, comment):
        self._hostSalt = hostSalt
        self._hostHash = hostHash
        super().__init__(keyType, publicKey, comment)

    @classmethod
    def fromString(cls, string):
        """
        Load a hashed entry from a string representing a line in a known_hosts
        file.

        @param string: A complete single line from a I{known_hosts} file,
            formatted as defined by OpenSSH.
        @type string: L{bytes}

        @raise DecodeError: if the key, the hostname, or the is not valid
            encoded as valid base64

        @raise InvalidEntry: if the entry does not have the right number of
            elements and is therefore invalid, or the host/hash portion contains
            more items than just the host and hash.

        @raise BadKeyError: if the key, once decoded from base64, is not
            actually an SSH key.

        @return: The newly created L{HashedEntry} instance, initialized with the
            information from C{string}.
        """
        stuff, keyType, key, comment = _extractCommon(string)
        saltAndHash = stuff[len(cls.MAGIC) :].split(b"|")
        if len(saltAndHash) != 2:
            raise InvalidEntry()
        hostSalt, hostHash = saltAndHash
        self = cls(a2b_base64(hostSalt), a2b_base64(hostHash), keyType, key, comment)
        return self

    def matchesHost(self, hostname):
        """
        Implement L{IKnownHostEntry.matchesHost} to compare the hash of the
        input to the stored hash.

        @param hostname: A hostname or IP address literal to check against this
            entry.
        @type hostname: L{bytes}

        @return: C{True} if this entry is for the given hostname or IP address,
            C{False} otherwise.
        @rtype: L{bool}
        """
        return hmac.compare_digest(
            _hmacedString(self._hostSalt, hostname), self._hostHash
        )

    def toString(self):
        """
        Implement L{IKnownHostEntry.toString} by base64-encoding the salt, host
        hash, and key.

        @return: The string representation of this entry, with the hostname part
            hashed.
        @rtype: L{bytes}
        """
        fields = [
            self.MAGIC
            + b"|".join([_b64encode(self._hostSalt), _b64encode(self._hostHash)]),
            self.keyType,
            _b64encode(self.publicKey.blob()),
        ]
        if self.comment is not None:
            fields.append(self.comment)
        return b" ".join(fields)


class KnownHostsFile:
    """
    A structured representation of an OpenSSH-format ~/.ssh/known_hosts file.

    @ivar _added: A list of L{IKnownHostEntry} providers which have been added
        to this instance in memory but not yet saved.

    @ivar _clobber: A flag indicating whether the current contents of the save
        path will be disregarded and potentially overwritten or not.  If
        C{True}, this will be done.  If C{False}, entries in the save path will
        be read and new entries will be saved by appending rather than
        overwriting.
    @type _clobber: L{bool}

    @ivar _savePath: See C{savePath} parameter of L{__init__}.
    """

    def __init__(self, savePath):
        """
        Create a new, empty KnownHostsFile.

        Unless you want to erase the current contents of C{savePath}, you want
        to use L{KnownHostsFile.fromPath} instead.

        @param savePath: The L{FilePath} to which to save new entries.
        @type savePath: L{FilePath}
        """
        self._added = []
        self._savePath = savePath
        self._clobber = True

    @property
    def savePath(self):
        """
        @see: C{savePath} parameter of L{__init__}
        """
        return self._savePath

    def iterentries(self):
        """
        Iterate over the host entries in this file.

        @return: An iterable the elements of which provide L{IKnownHostEntry}.
            There is an element for each entry in the file as well as an element
            for each added but not yet saved entry.
        @rtype: iterable of L{IKnownHostEntry} providers
        """
        for entry in self._added:
            yield entry

        if self._clobber:
            return

        try:
            fp = self._savePath.open()
        except OSError:
            return

        with fp:
            for line in fp:
                try:
                    if line.startswith(HashedEntry.MAGIC):
                        entry = HashedEntry.fromString(line)
                    else:
                        entry = PlainEntry.fromString(line)
                except (DecodeError, InvalidEntry, BadKeyError):
                    entry = UnparsedEntry(line)
                yield entry

    def hasHostKey(self, hostname, key):
        """
        Check for an entry with matching hostname and key.

        @param hostname: A hostname or IP address literal to check for.
        @type hostname: L{bytes}

        @param key: The public key to check for.
        @type key: L{Key}

        @return: C{True} if the given hostname and key are present in this file,
            C{False} if they are not.
        @rtype: L{bool}

        @raise HostKeyChanged: if the host key found for the given hostname
            does not match the given key.
        """
        for lineidx, entry in enumerate(self.iterentries(), -len(self._added)):
            if entry.matchesHost(hostname) and entry.keyType == key.sshType():
                if entry.matchesKey(key):
                    return True
                else:
                    # Notice that lineidx is 0-based but HostKeyChanged.lineno
                    # is 1-based.
                    if lineidx < 0:
                        line = None
                        path = None
                    else:
                        line = lineidx + 1
                        path = self._savePath
                    raise HostKeyChanged(entry, path, line)
        return False

    def verifyHostKey(self, ui, hostname, ip, key):
        """
        Verify the given host key for the given IP and host, asking for
        confirmation from, and notifying, the given UI about changes to this
        file.

        @param ui: The user interface to request an IP address from.

        @param hostname: The hostname that the user requested to connect to.

        @param ip: The string representation of the IP address that is actually
        being connected to.

        @param key: The public key of the server.

        @return: a L{Deferred} that fires with True when the key has been
            verified, or fires with an errback when the key either cannot be
            verified or has changed.
        @rtype: L{Deferred}
        """
        hhk = defer.execute(self.hasHostKey, hostname, key)

        def gotHasKey(result):
            if result:
                if not self.hasHostKey(ip, key):
                    ui.warn(
                        "Warning: Permanently added the %s host key for "
                        "IP address '%s' to the list of known hosts."
                        % (key.type(), nativeString(ip))
                    )
                    self.addHostKey(ip, key)
                    self.save()
                return result
            else:

                def promptResponse(response):
                    if response:
                        self.addHostKey(hostname, key)
                        self.addHostKey(ip, key)
                        self.save()
                        return response
                    else:
                        raise UserRejectedKey()

                keytype = key.type()

                if keytype == "EC":
                    keytype = "ECDSA"

                prompt = (
                    "The authenticity of host '%s (%s)' "
                    "can't be established.\n"
                    "%s key fingerprint is SHA256:%s.\n"
                    "Are you sure you want to continue connecting (yes/no)? "
                    % (
                        nativeString(hostname),
                        nativeString(ip),
                        keytype,
                        key.fingerprint(format=FingerprintFormats.SHA256_BASE64),
                    )
                )
                proceed = ui.prompt(prompt.encode(sys.getdefaultencoding()))
                return proceed.addCallback(promptResponse)

        return hhk.addCallback(gotHasKey)

    def addHostKey(self, hostname, key):
        """
        Add a new L{HashedEntry} to the key database.

        Note that you still need to call L{KnownHostsFile.save} if you wish
        these changes to be persisted.

        @param hostname: A hostname or IP address literal to associate with the
            new entry.
        @type hostname: L{bytes}

        @param key: The public key to associate with the new entry.
        @type key: L{Key}

        @return: The L{HashedEntry} that was added.
        @rtype: L{HashedEntry}
        """
        salt = secureRandom(20)
        keyType = key.sshType()
        entry = HashedEntry(salt, _hmacedString(salt, hostname), keyType, key, None)
        self._added.append(entry)
        return entry

    def save(self):
        """
        Save this L{KnownHostsFile} to the path it was loaded from.
        """
        p = self._savePath.parent()
        if not p.isdir():
            p.makedirs()

        if self._clobber:
            mode = "wb"
        else:
            mode = "ab"

        with self._savePath.open(mode) as hostsFileObj:
            if self._added:
                hostsFileObj.write(
                    b"\n".join([entry.toString() for entry in self._added]) + b"\n"
                )
                self._added = []
        self._clobber = False

    @classmethod
    def fromPath(cls, path):
        """
        Create a new L{KnownHostsFile}, potentially reading existing known
        hosts information from the given file.

        @param path: A path object to use for both reading contents from and
            later saving to.  If no file exists at this path, it is not an
            error; a L{KnownHostsFile} with no entries is returned.
        @type path: L{FilePath}

        @return: A L{KnownHostsFile} initialized with entries from C{path}.
        @rtype: L{KnownHostsFile}
        """
        knownHosts = cls(path)
        knownHosts._clobber = False
        return knownHosts


class ConsoleUI:
    """
    A UI object that can ask true/false questions and post notifications on the
    console, to be used during key verification.
    """

    def __init__(self, opener):
        """
        @param opener: A no-argument callable which should open a console
            binary-mode file-like object to be used for reading and writing.
            This initializes the C{opener} attribute.
        @type opener: callable taking no arguments and returning a read/write
            file-like object
        """
        self.opener = opener

    def prompt(self, text):
        """
        Write the given text as a prompt to the console output, then read a
        result from the console input.

        @param text: Something to present to a user to solicit a yes or no
            response.
        @type text: L{bytes}

        @return: a L{Deferred} which fires with L{True} when the user answers
            'yes' and L{False} when the user answers 'no'.  It may errback if
            there were any I/O errors.
        """
        d = defer.succeed(None)

        def body(ignored):
            with closing(self.opener()) as f:
                f.write(text)
                while True:
                    answer = f.readline().strip().lower()
                    if answer == b"yes":
                        return True
                    elif answer == b"no":
                        return False
                    else:
                        f.write(b"Please type 'yes' or 'no': ")

        return d.addCallback(body)

    def warn(self, text):
        """
        Notify the user (non-interactively) of the provided text, by writing it
        to the console.

        @param text: Some information the user is to be made aware of.
        @type text: L{bytes}
        """
        try:
            with closing(self.opener()) as f:
                f.write(text)
        except Exception:
            log.failure("Failed to write to console")
