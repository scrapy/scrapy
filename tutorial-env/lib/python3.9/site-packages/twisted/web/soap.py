# -*- test-case-name: twisted.web.test.test_soap -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
SOAP support for twisted.web.

Requires SOAPpy 0.10.1 or later.

Maintainer: Itamar Shtull-Trauring

Future plans:
SOAPContext support of some kind.
Pluggable method lookup policies.
"""

# SOAPpy
import SOAPpy  # type: ignore[import]

from twisted.internet import defer

# twisted imports
from twisted.web import client, resource, server


class SOAPPublisher(resource.Resource):
    """Publish SOAP methods.

    By default, publish methods beginning with 'soap_'. If the method
    has an attribute 'useKeywords', it well get the arguments passed
    as keyword args.
    """

    isLeaf = 1

    # override to change the encoding used for responses
    encoding = "UTF-8"

    def lookupFunction(self, functionName):
        """Lookup published SOAP function.

        Override in subclasses. Default behaviour - publish methods
        starting with soap_.

        @return: callable or None if not found.
        """
        return getattr(self, "soap_%s" % functionName, None)

    def render(self, request):
        """Handle a SOAP command."""
        data = request.content.read()

        p, header, body, attrs = SOAPpy.parseSOAPRPC(data, 1, 1, 1)

        methodName, args, kwargs = p._name, p._aslist, p._asdict

        # deal with changes in SOAPpy 0.11
        if callable(args):
            args = args()
        if callable(kwargs):
            kwargs = kwargs()

        function = self.lookupFunction(methodName)

        if not function:
            self._methodNotFound(request, methodName)
            return server.NOT_DONE_YET
        else:
            if hasattr(function, "useKeywords"):
                keywords = {}
                for k, v in kwargs.items():
                    keywords[str(k)] = v
                d = defer.maybeDeferred(function, **keywords)
            else:
                d = defer.maybeDeferred(function, *args)

        d.addCallback(self._gotResult, request, methodName)
        d.addErrback(self._gotError, request, methodName)
        return server.NOT_DONE_YET

    def _methodNotFound(self, request, methodName):
        response = SOAPpy.buildSOAP(
            SOAPpy.faultType(
                "%s:Client" % SOAPpy.NS.ENV_T, "Method %s not found" % methodName
            ),
            encoding=self.encoding,
        )
        self._sendResponse(request, response, status=500)

    def _gotResult(self, result, request, methodName):
        if not isinstance(result, SOAPpy.voidType):
            result = {"Result": result}
        response = SOAPpy.buildSOAP(
            kw={"%sResponse" % methodName: result}, encoding=self.encoding
        )
        self._sendResponse(request, response)

    def _gotError(self, failure, request, methodName):
        e = failure.value
        if isinstance(e, SOAPpy.faultType):
            fault = e
        else:
            fault = SOAPpy.faultType(
                "%s:Server" % SOAPpy.NS.ENV_T, "Method %s failed." % methodName
            )
        response = SOAPpy.buildSOAP(fault, encoding=self.encoding)
        self._sendResponse(request, response, status=500)

    def _sendResponse(self, request, response, status=200):
        request.setResponseCode(status)

        if self.encoding is not None:
            mimeType = 'text/xml; charset="%s"' % self.encoding
        else:
            mimeType = "text/xml"
        request.setHeader("Content-type", mimeType)
        request.setHeader("Content-length", str(len(response)))
        request.write(response)
        request.finish()


class Proxy:
    """A Proxy for making remote SOAP calls.

    Pass the URL of the remote SOAP server to the constructor.

    Use proxy.callRemote('foobar', 1, 2) to call remote method
    'foobar' with args 1 and 2, proxy.callRemote('foobar', x=1)
    will call foobar with named argument 'x'.
    """

    # at some point this should have encoding etc. kwargs
    def __init__(self, url, namespace=None, header=None):
        self.url = url
        self.namespace = namespace
        self.header = header

    def _cbGotResult(self, result):
        result = SOAPpy.parseSOAPRPC(result)
        if hasattr(result, "Result"):
            return result.Result
        elif len(result) == 1:
            ## SOAPpy 0.11.6 wraps the return results in a containing structure.
            ## This check added to make Proxy behaviour emulate SOAPProxy, which
            ## flattens the structure by default.
            ## This behaviour is OK because even singleton lists are wrapped in
            ## another singleton structType, which is almost always useless.
            return result[0]
        else:
            return result

    def callRemote(self, method, *args, **kwargs):
        payload = SOAPpy.buildSOAP(
            args=args,
            kw=kwargs,
            method=method,
            header=self.header,
            namespace=self.namespace,
        )
        return client.getPage(
            self.url,
            postdata=payload,
            method="POST",
            headers={"content-type": "text/xml", "SOAPAction": method},
        ).addCallback(self._cbGotResult)
