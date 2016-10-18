# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import absolute_import, division

from zope.interface import implementer

from twisted.internet import defer
from twisted.python.compat import unicode
from twisted.trial import unittest
from twisted.words.protocols.jabber import sasl, sasl_mechanisms, xmlstream, jid
from twisted.words.xish import domish

NS_XMPP_SASL = 'urn:ietf:params:xml:ns:xmpp-sasl'

@implementer(sasl_mechanisms.ISASLMechanism)
class DummySASLMechanism(object):
    """
    Dummy SASL mechanism.

    This just returns the initialResponse passed on creation, stores any
    challenges and replies with the value of C{response}.

    @ivar challenge: Last received challenge.
    @type challenge: C{unicode}.
    @ivar initialResponse: Initial response to be returned when requested
                           via C{getInitialResponse} or L{None}.
    @type initialResponse: C{unicode}
    """

    challenge = None
    name = u"DUMMY"
    response = b""

    def __init__(self, initialResponse):
        self.initialResponse = initialResponse

    def getInitialResponse(self):
        return self.initialResponse

    def getResponse(self, challenge):
        self.challenge = challenge
        return self.response


class DummySASLInitiatingInitializer(sasl.SASLInitiatingInitializer):
    """
    Dummy SASL Initializer for initiating entities.

    This hardwires the SASL mechanism to L{DummySASLMechanism}, that is
    instantiated with the value of C{initialResponse}.

    @ivar initialResponse: The initial response to be returned by the
                           dummy SASL mechanism or L{None}.
    @type initialResponse: C{unicode}.
    """

    initialResponse = None

    def setMechanism(self):
        self.mechanism = DummySASLMechanism(self.initialResponse)



class SASLInitiatingInitializerTests(unittest.TestCase):
    """
    Tests for L{sasl.SASLInitiatingInitializer}
    """

    def setUp(self):
        self.output = []

        self.authenticator = xmlstream.Authenticator()
        self.xmlstream = xmlstream.XmlStream(self.authenticator)
        self.xmlstream.send = self.output.append
        self.xmlstream.connectionMade()
        self.xmlstream.dataReceived(b"<stream:stream xmlns='jabber:client' "
                        b"xmlns:stream='http://etherx.jabber.org/streams' "
                        b"from='example.com' id='12345' version='1.0'>")
        self.init = DummySASLInitiatingInitializer(self.xmlstream)


    def test_onFailure(self):
        """
        Test that the SASL error condition is correctly extracted.
        """
        failure = domish.Element(('urn:ietf:params:xml:ns:xmpp-sasl',
                                  'failure'))
        failure.addElement('not-authorized')
        self.init._deferred = defer.Deferred()
        self.init.onFailure(failure)
        self.assertFailure(self.init._deferred, sasl.SASLAuthError)
        self.init._deferred.addCallback(lambda e:
                                        self.assertEqual('not-authorized',
                                                          e.condition))
        return self.init._deferred


    def test_sendAuthInitialResponse(self):
        """
        Test starting authentication with an initial response.
        """
        self.init.initialResponse = b"dummy"
        self.init.start()
        auth = self.output[0]
        self.assertEqual(NS_XMPP_SASL, auth.uri)
        self.assertEqual(u'auth', auth.name)
        self.assertEqual(u'DUMMY', auth['mechanism'])
        self.assertEqual(u'ZHVtbXk=', unicode(auth))


    def test_sendAuthNoInitialResponse(self):
        """
        Test starting authentication without an initial response.
        """
        self.init.initialResponse = None
        self.init.start()
        auth = self.output[0]
        self.assertEqual(u'', str(auth))


    def test_sendAuthEmptyInitialResponse(self):
        """
        Test starting authentication where the initial response is empty.
        """
        self.init.initialResponse = b""
        self.init.start()
        auth = self.output[0]
        self.assertEqual('=', unicode(auth))


    def test_onChallenge(self):
        """
        Test receiving a challenge message.
        """
        d = self.init.start()
        challenge = domish.Element((NS_XMPP_SASL, 'challenge'))
        challenge.addContent(u'bXkgY2hhbGxlbmdl')
        self.init.onChallenge(challenge)
        self.assertEqual(b'my challenge', self.init.mechanism.challenge)
        self.init.onSuccess(None)
        return d


    def test_onChallengeResponse(self):
        """
        A non-empty response gets encoded and included as character data.
        """
        d = self.init.start()
        challenge = domish.Element((NS_XMPP_SASL, 'challenge'))
        challenge.addContent(u'bXkgY2hhbGxlbmdl')
        self.init.mechanism.response = b"response"
        self.init.onChallenge(challenge)
        response = self.output[1]
        self.assertEqual(u'cmVzcG9uc2U=', unicode(response))
        self.init.onSuccess(None)
        return d


    def test_onChallengeEmpty(self):
        """
        Test receiving an empty challenge message.
        """
        d = self.init.start()
        challenge = domish.Element((NS_XMPP_SASL, 'challenge'))
        self.init.onChallenge(challenge)
        self.assertEqual(b'', self.init.mechanism.challenge)
        self.init.onSuccess(None)
        return d


    def test_onChallengeIllegalPadding(self):
        """
        Test receiving a challenge message with illegal padding.
        """
        d = self.init.start()
        challenge = domish.Element((NS_XMPP_SASL, 'challenge'))
        challenge.addContent(u'bXkg=Y2hhbGxlbmdl')
        self.init.onChallenge(challenge)
        self.assertFailure(d, sasl.SASLIncorrectEncodingError)
        return d


    def test_onChallengeIllegalCharacters(self):
        """
        Test receiving a challenge message with illegal characters.
        """
        d = self.init.start()
        challenge = domish.Element((NS_XMPP_SASL, 'challenge'))
        challenge.addContent(u'bXkg*Y2hhbGxlbmdl')
        self.init.onChallenge(challenge)
        self.assertFailure(d, sasl.SASLIncorrectEncodingError)
        return d


    def test_onChallengeMalformed(self):
        """
        Test receiving a malformed challenge message.
        """
        d = self.init.start()
        challenge = domish.Element((NS_XMPP_SASL, 'challenge'))
        challenge.addContent(u'a')
        self.init.onChallenge(challenge)
        self.assertFailure(d, sasl.SASLIncorrectEncodingError)
        return d


class SASLInitiatingInitializerSetMechanismTests(unittest.TestCase):
    """
    Test for L{sasl.SASLInitiatingInitializer.setMechanism}.
    """

    def setUp(self):
        self.output = []

        self.authenticator = xmlstream.Authenticator()
        self.xmlstream = xmlstream.XmlStream(self.authenticator)
        self.xmlstream.send = self.output.append
        self.xmlstream.connectionMade()
        self.xmlstream.dataReceived("<stream:stream xmlns='jabber:client' "
                        "xmlns:stream='http://etherx.jabber.org/streams' "
                        "from='example.com' id='12345' version='1.0'>")

        self.init = sasl.SASLInitiatingInitializer(self.xmlstream)


    def _setMechanism(self, name):
        """
        Set up the XML Stream to have a SASL feature with the given mechanism.
        """
        feature = domish.Element((NS_XMPP_SASL, 'mechanisms'))
        feature.addElement('mechanism', content=name)
        self.xmlstream.features[(feature.uri, feature.name)] = feature

        self.init.setMechanism()
        return self.init.mechanism.name


    def test_anonymous(self):
        """
        Test setting ANONYMOUS as the authentication mechanism.
        """
        self.authenticator.jid = jid.JID('example.com')
        self.authenticator.password = None
        name = u"ANONYMOUS"

        self.assertEqual(name, self._setMechanism(name))


    def test_plain(self):
        """
        Test setting PLAIN as the authentication mechanism.
        """
        self.authenticator.jid = jid.JID('test@example.com')
        self.authenticator.password = 'secret'
        name = u"PLAIN"

        self.assertEqual(name, self._setMechanism(name))


    def test_digest(self):
        """
        Test setting DIGEST-MD5 as the authentication mechanism.
        """
        self.authenticator.jid = jid.JID('test@example.com')
        self.authenticator.password = 'secret'
        name = u"DIGEST-MD5"

        self.assertEqual(name, self._setMechanism(name))


    def test_notAcceptable(self):
        """
        Test using an unacceptable SASL authentication mechanism.
        """

        self.authenticator.jid = jid.JID('test@example.com')
        self.authenticator.password = u'secret'

        self.assertRaises(sasl.SASLNoAcceptableMechanism,
                          self._setMechanism, u'SOMETHING_UNACCEPTABLE')


    def test_notAcceptableWithoutUser(self):
        """
        Test using an unacceptable SASL authentication mechanism with no JID.
        """
        self.authenticator.jid = jid.JID('example.com')
        self.authenticator.password = u'secret'

        self.assertRaises(sasl.SASLNoAcceptableMechanism,
                          self._setMechanism, u'SOMETHING_UNACCEPTABLE')
