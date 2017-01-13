# -*- test-case-name: twisted.words.test.test_jabbersaslmechanisms -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Protocol agnostic implementations of SASL authentication mechanisms.
"""

from __future__ import absolute_import, division

import binascii, random, time, os
from hashlib import md5

from zope.interface import Interface, Attribute, implementer

from twisted.python.compat import iteritems, networkString


class ISASLMechanism(Interface):
    name = Attribute("""Common name for the SASL Mechanism.""")

    def getInitialResponse():
        """
        Get the initial client response, if defined for this mechanism.

        @return: initial client response string.
        @rtype: C{str}.
        """


    def getResponse(challenge):
        """
        Get the response to a server challenge.

        @param challenge: server challenge.
        @type challenge: C{str}.
        @return: client response.
        @rtype: C{str}.
        """



@implementer(ISASLMechanism)
class Anonymous(object):
    """
    Implements the ANONYMOUS SASL authentication mechanism.

    This mechanism is defined in RFC 2245.
    """
    name = 'ANONYMOUS'

    def getInitialResponse(self):
        return None



@implementer(ISASLMechanism)
class Plain(object):
    """
    Implements the PLAIN SASL authentication mechanism.

    The PLAIN SASL authentication mechanism is defined in RFC 2595.
    """
    name = 'PLAIN'

    def __init__(self, authzid, authcid, password):
        """
        @param authzid: The authorization identity.
        @type authzid: L{unicode}

        @param authcid: The authentication identity.
        @type authcid: L{unicode}

        @param password: The plain-text password.
        @type password: L{unicode}
        """

        self.authzid = authzid or u''
        self.authcid = authcid or u''
        self.password = password or u''


    def getInitialResponse(self):
        return (self.authzid.encode('utf-8') + b"\x00" +
                self.authcid.encode('utf-8') + b"\x00" +
                self.password.encode('utf-8'))



@implementer(ISASLMechanism)
class DigestMD5(object):
    """
    Implements the DIGEST-MD5 SASL authentication mechanism.

    The DIGEST-MD5 SASL authentication mechanism is defined in RFC 2831.
    """
    name = 'DIGEST-MD5'

    def __init__(self, serv_type, host, serv_name, username, password):
        """
        @param serv_type: An indication of what kind of server authentication
            is being attempted against.  For example, C{u"xmpp"}.
        @type serv_type: C{unicode}

        @param host: The authentication hostname.  Also known as the realm.
            This is used as a scope to help select the right credentials.
        @type host: C{unicode}

        @param serv_name: An additional identifier for the server.
        @type serv_name: C{unicode}

        @param username: The authentication username to use to respond to a
            challenge.
        @type username: C{unicode}

        @param username: The authentication password to use to respond to a
            challenge.
        @type password: C{unicode}
        """
        self.username = username
        self.password = password
        self.defaultRealm = host

        self.digest_uri = u'%s/%s' % (serv_type, host)
        if serv_name is not None:
            self.digest_uri += u'/%s' % (serv_name,)


    def getInitialResponse(self):
        return None


    def getResponse(self, challenge):
        directives = self._parse(challenge)

        # Compat for implementations that do not send this along with
        # a successful authentication.
        if b'rspauth' in directives:
            return b''

        charset = directives[b'charset'].decode('ascii')

        try:
            realm = directives[b'realm']
        except KeyError:
            realm = self.defaultRealm.encode(charset)

        return self._genResponse(charset,
                                 realm,
                                 directives[b'nonce'])


    def _parse(self, challenge):
        """
        Parses the server challenge.

        Splits the challenge into a dictionary of directives with values.

        @return: challenge directives and their values.
        @rtype: C{dict} of C{str} to C{str}.
        """
        s = challenge
        paramDict = {}
        cur = 0
        remainingParams = True
        while remainingParams:
            # Parse a param. We can't just split on commas, because there can
            # be some commas inside (quoted) param values, e.g.:
            # qop="auth,auth-int"

            middle = s.index(b"=", cur)
            name = s[cur:middle].lstrip()
            middle += 1
            if s[middle:middle+1] == b'"':
                middle += 1
                end = s.index(b'"', middle)
                value = s[middle:end]
                cur = s.find(b',', end) + 1
                if cur == 0:
                    remainingParams = False
            else:
                end = s.find(b',', middle)
                if end == -1:
                    value = s[middle:].rstrip()
                    remainingParams = False
                else:
                    value = s[middle:end].rstrip()
                cur = end + 1
            paramDict[name] = value

        for param in (b'qop', b'cipher'):
            if param in paramDict:
                paramDict[param] = paramDict[param].split(b',')

        return paramDict

    def _unparse(self, directives):
        """
        Create message string from directives.

        @param directives: dictionary of directives (names to their values).
                           For certain directives, extra quotes are added, as
                           needed.
        @type directives: C{dict} of C{str} to C{str}
        @return: message string.
        @rtype: C{str}.
        """

        directive_list = []
        for name, value in iteritems(directives):
            if name in (b'username', b'realm', b'cnonce',
                        b'nonce', b'digest-uri', b'authzid', b'cipher'):
                directive = name + b'=' + value
            else:
                directive = name + b'=' + value

            directive_list.append(directive)

        return b','.join(directive_list)


    def _calculateResponse(self, cnonce, nc, nonce,
                            username, password, realm, uri):
        """
        Calculates response with given encoded parameters.

        @return: The I{response} field of a response to a Digest-MD5 challenge
            of the given parameters.
        @rtype: L{bytes}
        """
        def H(s):
            return md5(s).digest()

        def HEX(n):
            return binascii.b2a_hex(n)

        def KD(k, s):
            return H(k + b':' + s)

        a1 = (H(username + b":" + realm + b":" + password) + b":" +
              nonce + b":" +
              cnonce)
        a2 = b"AUTHENTICATE:" + uri

        response = HEX(KD(HEX(H(a1)),
                       nonce + b":" + nc + b":" + cnonce + b":" +
                       b"auth" + b":" + HEX(H(a2))))
        return response


    def _genResponse(self, charset, realm, nonce):
        """
        Generate response-value.

        Creates a response to a challenge according to section 2.1.2.1 of
        RFC 2831 using the C{charset}, C{realm} and C{nonce} directives
        from the challenge.
        """
        try:
            username = self.username.encode(charset)
            password = self.password.encode(charset)
            digest_uri = self.digest_uri.encode(charset)
        except UnicodeError:
            # TODO - add error checking
            raise

        nc = networkString('%08x' % (1,)) # TODO: support subsequent auth.
        cnonce = self._gen_nonce()
        qop = b'auth'

        # TODO - add support for authzid
        response = self._calculateResponse(cnonce, nc, nonce,
                                           username, password, realm,
                                           digest_uri)

        directives = {b'username': username,
                      b'realm' : realm,
                      b'nonce' : nonce,
                      b'cnonce' : cnonce,
                      b'nc' : nc,
                      b'qop' : qop,
                      b'digest-uri': digest_uri,
                      b'response': response,
                      b'charset': charset.encode('ascii')}

        return self._unparse(directives)


    def _gen_nonce(self):
        nonceString = "%f:%f:%d" % (random.random(), time.time(), os.getpid())
        nonceBytes = networkString(nonceString)
        return md5(nonceBytes).hexdigest().encode('ascii')
