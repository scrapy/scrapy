# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.web._auth}.
"""

from __future__ import division, absolute_import

import base64

from zope.interface import implementer
from zope.interface.verify import verifyObject

from twisted.trial import unittest

from twisted.python.failure import Failure
from twisted.internet.error import ConnectionDone
from twisted.internet.address import IPv4Address

from twisted.cred import error, portal
from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse
from twisted.cred.checkers import ANONYMOUS, AllowAnonymousAccess
from twisted.cred.credentials import IUsernamePassword

from twisted.web.iweb import ICredentialFactory
from twisted.web.resource import IResource, Resource, getChildForRequest
from twisted.web._auth import basic, digest
from twisted.web._auth.wrapper import HTTPAuthSessionWrapper, UnauthorizedResource
from twisted.web._auth.basic import BasicCredentialFactory

from twisted.web.server import NOT_DONE_YET
from twisted.web.static import Data

from twisted.web.test.test_web import DummyRequest


def b64encode(s):
    return base64.b64encode(s).strip()


class BasicAuthTestsMixin:
    """
    L{TestCase} mixin class which defines a number of tests for
    L{basic.BasicCredentialFactory}.  Because this mixin defines C{setUp}, it
    must be inherited before L{TestCase}.
    """
    def setUp(self):
        self.request = self.makeRequest()
        self.realm = b'foo'
        self.username = b'dreid'
        self.password = b'S3CuR1Ty'
        self.credentialFactory = basic.BasicCredentialFactory(self.realm)


    def makeRequest(self, method=b'GET', clientAddress=None):
        """
        Create a request object to be passed to
        L{basic.BasicCredentialFactory.decode} along with a response value.
        Override this in a subclass.
        """
        raise NotImplementedError("%r did not implement makeRequest" % (
                self.__class__,))


    def test_interface(self):
        """
        L{BasicCredentialFactory} implements L{ICredentialFactory}.
        """
        self.assertTrue(
            verifyObject(ICredentialFactory, self.credentialFactory))


    def test_usernamePassword(self):
        """
        L{basic.BasicCredentialFactory.decode} turns a base64-encoded response
        into a L{UsernamePassword} object with a password which reflects the
        one which was encoded in the response.
        """
        response = b64encode(b''.join([self.username, b':', self.password]))

        creds = self.credentialFactory.decode(response, self.request)
        self.assertTrue(IUsernamePassword.providedBy(creds))
        self.assertTrue(creds.checkPassword(self.password))
        self.assertFalse(creds.checkPassword(self.password + b'wrong'))


    def test_incorrectPadding(self):
        """
        L{basic.BasicCredentialFactory.decode} decodes a base64-encoded
        response with incorrect padding.
        """
        response = b64encode(b''.join([self.username, b':', self.password]))
        response = response.strip(b'=')

        creds = self.credentialFactory.decode(response, self.request)
        self.assertTrue(verifyObject(IUsernamePassword, creds))
        self.assertTrue(creds.checkPassword(self.password))


    def test_invalidEncoding(self):
        """
        L{basic.BasicCredentialFactory.decode} raises L{LoginFailed} if passed
        a response which is not base64-encoded.
        """
        response = b'x' # one byte cannot be valid base64 text
        self.assertRaises(
            error.LoginFailed,
            self.credentialFactory.decode, response, self.makeRequest())


    def test_invalidCredentials(self):
        """
        L{basic.BasicCredentialFactory.decode} raises L{LoginFailed} when
        passed a response which is not valid base64-encoded text.
        """
        response = b64encode(b'123abc+/')
        self.assertRaises(
            error.LoginFailed,
            self.credentialFactory.decode,
            response, self.makeRequest())


class RequestMixin:
    def makeRequest(self, method=b'GET', clientAddress=None):
        """
        Create a L{DummyRequest} (change me to create a
        L{twisted.web.http.Request} instead).
        """
        request = DummyRequest(b'/')
        request.method = method
        request.client = clientAddress
        return request



class BasicAuthTests(RequestMixin, BasicAuthTestsMixin, unittest.TestCase):
    """
    Basic authentication tests which use L{twisted.web.http.Request}.
    """



class DigestAuthTests(RequestMixin, unittest.TestCase):
    """
    Digest authentication tests which use L{twisted.web.http.Request}.
    """

    def setUp(self):
        """
        Create a DigestCredentialFactory for testing
        """
        self.realm = b"test realm"
        self.algorithm = b"md5"
        self.credentialFactory = digest.DigestCredentialFactory(
            self.algorithm, self.realm)
        self.request = self.makeRequest()


    def test_decode(self):
        """
        L{digest.DigestCredentialFactory.decode} calls the C{decode} method on
        L{twisted.cred.digest.DigestCredentialFactory} with the HTTP method and
        host of the request.
        """
        host = b'169.254.0.1'
        method = b'GET'
        done = [False]
        response = object()
        def check(_response, _method, _host):
            self.assertEqual(response, _response)
            self.assertEqual(method, _method)
            self.assertEqual(host, _host)
            done[0] = True

        self.patch(self.credentialFactory.digest, 'decode', check)
        req = self.makeRequest(method, IPv4Address('TCP', host, 81))
        self.credentialFactory.decode(response, req)
        self.assertTrue(done[0])


    def test_interface(self):
        """
        L{DigestCredentialFactory} implements L{ICredentialFactory}.
        """
        self.assertTrue(
            verifyObject(ICredentialFactory, self.credentialFactory))


    def test_getChallenge(self):
        """
        The challenge issued by L{DigestCredentialFactory.getChallenge} must
        include C{'qop'}, C{'realm'}, C{'algorithm'}, C{'nonce'}, and
        C{'opaque'} keys.  The values for the C{'realm'} and C{'algorithm'}
        keys must match the values supplied to the factory's initializer.
        None of the values may have newlines in them.
        """
        challenge = self.credentialFactory.getChallenge(self.request)
        self.assertEqual(challenge['qop'], b'auth')
        self.assertEqual(challenge['realm'], b'test realm')
        self.assertEqual(challenge['algorithm'], b'md5')
        self.assertIn('nonce', challenge)
        self.assertIn('opaque', challenge)
        for v in challenge.values():
            self.assertNotIn(b'\n', v)


    def test_getChallengeWithoutClientIP(self):
        """
        L{DigestCredentialFactory.getChallenge} can issue a challenge even if
        the L{Request} it is passed returns L{None} from C{getClientIP}.
        """
        request = self.makeRequest(b'GET', None)
        challenge = self.credentialFactory.getChallenge(request)
        self.assertEqual(challenge['qop'], b'auth')
        self.assertEqual(challenge['realm'], b'test realm')
        self.assertEqual(challenge['algorithm'], b'md5')
        self.assertIn('nonce', challenge)
        self.assertIn('opaque', challenge)



class UnauthorizedResourceTests(unittest.TestCase):
    """
    Tests for L{UnauthorizedResource}.
    """
    def test_getChildWithDefault(self):
        """
        An L{UnauthorizedResource} is every child of itself.
        """
        resource = UnauthorizedResource([])
        self.assertIdentical(
            resource.getChildWithDefault("foo", None), resource)
        self.assertIdentical(
            resource.getChildWithDefault("bar", None), resource)


    def _unauthorizedRenderTest(self, request):
        """
        Render L{UnauthorizedResource} for the given request object and verify
        that the response code is I{Unauthorized} and that a I{WWW-Authenticate}
        header is set in the response containing a challenge.
        """
        resource = UnauthorizedResource([
                BasicCredentialFactory('example.com')])
        request.render(resource)
        self.assertEqual(request.responseCode, 401)
        self.assertEqual(
            request.responseHeaders.getRawHeaders(b'www-authenticate'),
            [b'basic realm="example.com"'])


    def test_render(self):
        """
        L{UnauthorizedResource} renders with a 401 response code and a
        I{WWW-Authenticate} header and puts a simple unauthorized message
        into the response body.
        """
        request = DummyRequest([b''])
        self._unauthorizedRenderTest(request)
        self.assertEqual(b'Unauthorized', b''.join(request.written))


    def test_renderHEAD(self):
        """
        The rendering behavior of L{UnauthorizedResource} for a I{HEAD} request
        is like its handling of a I{GET} request, but no response body is
        written.
        """
        request = DummyRequest([b''])
        request.method = b'HEAD'
        self._unauthorizedRenderTest(request)
        self.assertEqual(b'', b''.join(request.written))


    def test_renderQuotesRealm(self):
        """
        The realm value included in the I{WWW-Authenticate} header set in
        the response when L{UnauthorizedResounrce} is rendered has quotes
        and backslashes escaped.
        """
        resource = UnauthorizedResource([
                BasicCredentialFactory('example\\"foo')])
        request = DummyRequest([b''])
        request.render(resource)
        self.assertEqual(
            request.responseHeaders.getRawHeaders(b'www-authenticate'),
            [b'basic realm="example\\\\\\"foo"'])



implementer(portal.IRealm)
class Realm(object):
    """
    A simple L{IRealm} implementation which gives out L{WebAvatar} for any
    avatarId.

    @type loggedIn: C{int}
    @ivar loggedIn: The number of times C{requestAvatar} has been invoked for
        L{IResource}.

    @type loggedOut: C{int}
    @ivar loggedOut: The number of times the logout callback has been invoked.
    """

    def __init__(self, avatarFactory):
        self.loggedOut = 0
        self.loggedIn = 0
        self.avatarFactory = avatarFactory


    def requestAvatar(self, avatarId, mind, *interfaces):
        if IResource in interfaces:
            self.loggedIn += 1
            return IResource, self.avatarFactory(avatarId), self.logout
        raise NotImplementedError()


    def logout(self):
        self.loggedOut += 1



class HTTPAuthHeaderTests(unittest.TestCase):
    """
    Tests for L{HTTPAuthSessionWrapper}.
    """
    makeRequest = DummyRequest

    def setUp(self):
        """
        Create a realm, portal, and L{HTTPAuthSessionWrapper} to use in the tests.
        """
        self.username = b'foo bar'
        self.password = b'bar baz'
        self.avatarContent = b"contents of the avatar resource itself"
        self.childName = b"foo-child"
        self.childContent = b"contents of the foo child of the avatar"
        self.checker = InMemoryUsernamePasswordDatabaseDontUse()
        self.checker.addUser(self.username, self.password)
        self.avatar = Data(self.avatarContent, 'text/plain')
        self.avatar.putChild(
            self.childName, Data(self.childContent, 'text/plain'))
        self.avatars = {self.username: self.avatar}
        self.realm = Realm(self.avatars.get)
        self.portal = portal.Portal(self.realm, [self.checker])
        self.credentialFactories = []
        self.wrapper = HTTPAuthSessionWrapper(
            self.portal, self.credentialFactories)


    def _authorizedBasicLogin(self, request):
        """
        Add an I{basic authorization} header to the given request and then
        dispatch it, starting from C{self.wrapper} and returning the resulting
        L{IResource}.
        """
        authorization = b64encode(self.username + b':' + self.password)
        request.requestHeaders.addRawHeader(b'authorization',
                                            b'Basic ' + authorization)
        return getChildForRequest(self.wrapper, request)


    def test_getChildWithDefault(self):
        """
        Resource traversal which encounters an L{HTTPAuthSessionWrapper}
        results in an L{UnauthorizedResource} instance when the request does
        not have the required I{Authorization} headers.
        """
        request = self.makeRequest([self.childName])
        child = getChildForRequest(self.wrapper, request)
        d = request.notifyFinish()
        def cbFinished(result):
            self.assertEqual(request.responseCode, 401)
        d.addCallback(cbFinished)
        request.render(child)
        return d


    def _invalidAuthorizationTest(self, response):
        """
        Create a request with the given value as the value of an
        I{Authorization} header and perform resource traversal with it,
        starting at C{self.wrapper}.  Assert that the result is a 401 response
        code.  Return a L{Deferred} which fires when this is all done.
        """
        self.credentialFactories.append(BasicCredentialFactory('example.com'))
        request = self.makeRequest([self.childName])
        request.requestHeaders.addRawHeader(b'authorization', response)
        child = getChildForRequest(self.wrapper, request)
        d = request.notifyFinish()
        def cbFinished(result):
            self.assertEqual(request.responseCode, 401)
        d.addCallback(cbFinished)
        request.render(child)
        return d


    def test_getChildWithDefaultUnauthorizedUser(self):
        """
        Resource traversal which enouncters an L{HTTPAuthSessionWrapper}
        results in an L{UnauthorizedResource} when the request has an
        I{Authorization} header with a user which does not exist.
        """
        return self._invalidAuthorizationTest(
            b'Basic ' + b64encode(b'foo:bar'))


    def test_getChildWithDefaultUnauthorizedPassword(self):
        """
        Resource traversal which enouncters an L{HTTPAuthSessionWrapper}
        results in an L{UnauthorizedResource} when the request has an
        I{Authorization} header with a user which exists and the wrong
        password.
        """
        return self._invalidAuthorizationTest(
            b'Basic ' + b64encode(self.username + b':bar'))


    def test_getChildWithDefaultUnrecognizedScheme(self):
        """
        Resource traversal which enouncters an L{HTTPAuthSessionWrapper}
        results in an L{UnauthorizedResource} when the request has an
        I{Authorization} header with an unrecognized scheme.
        """
        return self._invalidAuthorizationTest(b'Quux foo bar baz')


    def test_getChildWithDefaultAuthorized(self):
        """
        Resource traversal which encounters an L{HTTPAuthSessionWrapper}
        results in an L{IResource} which renders the L{IResource} avatar
        retrieved from the portal when the request has a valid I{Authorization}
        header.
        """
        self.credentialFactories.append(BasicCredentialFactory('example.com'))
        request = self.makeRequest([self.childName])
        child = self._authorizedBasicLogin(request)
        d = request.notifyFinish()
        def cbFinished(ignored):
            self.assertEqual(request.written, [self.childContent])
        d.addCallback(cbFinished)
        request.render(child)
        return d


    def test_renderAuthorized(self):
        """
        Resource traversal which terminates at an L{HTTPAuthSessionWrapper}
        and includes correct authentication headers results in the
        L{IResource} avatar (not one of its children) retrieved from the
        portal being rendered.
        """
        self.credentialFactories.append(BasicCredentialFactory('example.com'))
        # Request it exactly, not any of its children.
        request = self.makeRequest([])
        child = self._authorizedBasicLogin(request)
        d = request.notifyFinish()
        def cbFinished(ignored):
            self.assertEqual(request.written, [self.avatarContent])
        d.addCallback(cbFinished)
        request.render(child)
        return d


    def test_getChallengeCalledWithRequest(self):
        """
        When L{HTTPAuthSessionWrapper} finds an L{ICredentialFactory} to issue
        a challenge, it calls the C{getChallenge} method with the request as an
        argument.
        """
        @implementer(ICredentialFactory)
        class DumbCredentialFactory(object):
            scheme = b'dumb'

            def __init__(self):
                self.requests = []

            def getChallenge(self, request):
                self.requests.append(request)
                return {}

        factory = DumbCredentialFactory()
        self.credentialFactories.append(factory)
        request = self.makeRequest([self.childName])
        child = getChildForRequest(self.wrapper, request)
        d = request.notifyFinish()
        def cbFinished(ignored):
            self.assertEqual(factory.requests, [request])
        d.addCallback(cbFinished)
        request.render(child)
        return d


    def _logoutTest(self):
        """
        Issue a request for an authentication-protected resource using valid
        credentials and then return the C{DummyRequest} instance which was
        used.

        This is a helper for tests about the behavior of the logout
        callback.
        """
        self.credentialFactories.append(BasicCredentialFactory('example.com'))

        class SlowerResource(Resource):
            def render(self, request):
                return NOT_DONE_YET

        self.avatar.putChild(self.childName, SlowerResource())
        request = self.makeRequest([self.childName])
        child = self._authorizedBasicLogin(request)
        request.render(child)
        self.assertEqual(self.realm.loggedOut, 0)
        return request


    def test_logout(self):
        """
        The realm's logout callback is invoked after the resource is rendered.
        """
        request = self._logoutTest()
        request.finish()
        self.assertEqual(self.realm.loggedOut, 1)


    def test_logoutOnError(self):
        """
        The realm's logout callback is also invoked if there is an error
        generating the response (for example, if the client disconnects
        early).
        """
        request = self._logoutTest()
        request.processingFailed(
            Failure(ConnectionDone("Simulated disconnect")))
        self.assertEqual(self.realm.loggedOut, 1)


    def test_decodeRaises(self):
        """
        Resource traversal which enouncters an L{HTTPAuthSessionWrapper}
        results in an L{UnauthorizedResource} when the request has a I{Basic
        Authorization} header which cannot be decoded using base64.
        """
        self.credentialFactories.append(BasicCredentialFactory('example.com'))
        request = self.makeRequest([self.childName])
        request.requestHeaders.addRawHeader(b'authorization', b'Basic decode should fail')
        child = getChildForRequest(self.wrapper, request)
        self.assertIsInstance(child, UnauthorizedResource)


    def test_selectParseResponse(self):
        """
        L{HTTPAuthSessionWrapper._selectParseHeader} returns a two-tuple giving
        the L{ICredentialFactory} to use to parse the header and a string
        containing the portion of the header which remains to be parsed.
        """
        basicAuthorization = b'Basic abcdef123456'
        self.assertEqual(
            self.wrapper._selectParseHeader(basicAuthorization),
            (None, None))
        factory = BasicCredentialFactory('example.com')
        self.credentialFactories.append(factory)
        self.assertEqual(
            self.wrapper._selectParseHeader(basicAuthorization),
            (factory, b'abcdef123456'))


    def test_unexpectedDecodeError(self):
        """
        Any unexpected exception raised by the credential factory's C{decode}
        method results in a 500 response code and causes the exception to be
        logged.
        """
        class UnexpectedException(Exception):
            pass

        class BadFactory(object):
            scheme = b'bad'

            def getChallenge(self, client):
                return {}

            def decode(self, response, request):
                raise UnexpectedException()

        self.credentialFactories.append(BadFactory())
        request = self.makeRequest([self.childName])
        request.requestHeaders.addRawHeader(b'authorization', b'Bad abc')
        child = getChildForRequest(self.wrapper, request)
        request.render(child)
        self.assertEqual(request.responseCode, 500)
        self.assertEqual(len(self.flushLoggedErrors(UnexpectedException)), 1)


    def test_unexpectedLoginError(self):
        """
        Any unexpected failure from L{Portal.login} results in a 500 response
        code and causes the failure to be logged.
        """
        class UnexpectedException(Exception):
            pass

        class BrokenChecker(object):
            credentialInterfaces = (IUsernamePassword,)

            def requestAvatarId(self, credentials):
                raise UnexpectedException()

        self.portal.registerChecker(BrokenChecker())
        self.credentialFactories.append(BasicCredentialFactory('example.com'))
        request = self.makeRequest([self.childName])
        child = self._authorizedBasicLogin(request)
        request.render(child)
        self.assertEqual(request.responseCode, 500)
        self.assertEqual(len(self.flushLoggedErrors(UnexpectedException)), 1)


    def test_anonymousAccess(self):
        """
        Anonymous requests are allowed if a L{Portal} has an anonymous checker
        registered.
        """
        unprotectedContents = b"contents of the unprotected child resource"

        self.avatars[ANONYMOUS] = Resource()
        self.avatars[ANONYMOUS].putChild(
            self.childName, Data(unprotectedContents, 'text/plain'))
        self.portal.registerChecker(AllowAnonymousAccess())

        self.credentialFactories.append(BasicCredentialFactory('example.com'))
        request = self.makeRequest([self.childName])
        child = getChildForRequest(self.wrapper, request)
        d = request.notifyFinish()
        def cbFinished(ignored):
            self.assertEqual(request.written, [unprotectedContents])
        d.addCallback(cbFinished)
        request.render(child)
        return d
