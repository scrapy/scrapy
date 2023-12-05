# -*- test-case-name: twisted.web.test.test_cgi -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
I hold resource classes and helper classes that deal with CGI scripts.
"""

# System Imports
import os
import urllib

# Twisted Imports
from twisted.internet import protocol
from twisted.logger import Logger
from twisted.python import filepath
from twisted.spread import pb
from twisted.web import http, resource, server, static


class CGIDirectory(resource.Resource, filepath.FilePath):
    def __init__(self, pathname):
        resource.Resource.__init__(self)
        filepath.FilePath.__init__(self, pathname)

    def getChild(self, path, request):
        fnp = self.child(path)
        if not fnp.exists():
            return static.File.childNotFound
        elif fnp.isdir():
            return CGIDirectory(fnp.path)
        else:
            return CGIScript(fnp.path)

    def render(self, request):
        notFound = resource.NoResource(
            "CGI directories do not support directory listing."
        )
        return notFound.render(request)


class CGIScript(resource.Resource):
    """
    L{CGIScript} is a resource which runs child processes according to the CGI
    specification.

    The implementation is complex due to the fact that it requires asynchronous
    IPC with an external process with an unpleasant protocol.
    """

    isLeaf = 1

    def __init__(self, filename, registry=None, reactor=None):
        """
        Initialize, with the name of a CGI script file.
        """
        self.filename = filename
        if reactor is None:
            # This installs a default reactor, if None was installed before.
            # We do a late import here, so that importing the current module
            # won't directly trigger installing a default reactor.
            from twisted.internet import reactor
        self._reactor = reactor

    def render(self, request):
        """
        Do various things to conform to the CGI specification.

        I will set up the usual slew of environment variables, then spin off a
        process.

        @type request: L{twisted.web.http.Request}
        @param request: An HTTP request.
        """
        scriptName = b"/" + b"/".join(request.prepath)
        serverName = request.getRequestHostname().split(b":")[0]
        env = {
            "SERVER_SOFTWARE": server.version,
            "SERVER_NAME": serverName,
            "GATEWAY_INTERFACE": "CGI/1.1",
            "SERVER_PROTOCOL": request.clientproto,
            "SERVER_PORT": str(request.getHost().port),
            "REQUEST_METHOD": request.method,
            "SCRIPT_NAME": scriptName,
            "SCRIPT_FILENAME": self.filename,
            "REQUEST_URI": request.uri,
        }

        ip = request.getClientAddress().host
        if ip is not None:
            env["REMOTE_ADDR"] = ip
        pp = request.postpath
        if pp:
            env["PATH_INFO"] = "/" + "/".join(pp)

        if hasattr(request, "content"):
            # 'request.content' is either a StringIO or a TemporaryFile, and
            # the file pointer is sitting at the beginning (seek(0,0))
            request.content.seek(0, 2)
            length = request.content.tell()
            request.content.seek(0, 0)
            env["CONTENT_LENGTH"] = str(length)

        try:
            qindex = request.uri.index(b"?")
        except ValueError:
            env["QUERY_STRING"] = ""
            qargs = []
        else:
            qs = env["QUERY_STRING"] = request.uri[qindex + 1 :]
            if b"=" in qs:
                qargs = []
            else:
                qargs = [urllib.parse.unquote(x.decode()) for x in qs.split(b"+")]

        # Propagate HTTP headers
        for title, header in request.getAllHeaders().items():
            envname = title.replace(b"-", b"_").upper()
            if title not in (b"content-type", b"content-length", b"proxy"):
                envname = b"HTTP_" + envname
            env[envname] = header
        # Propagate our environment
        for key, value in os.environ.items():
            if key not in env:
                env[key] = value
        # And they're off!
        self.runProcess(env, request, qargs)
        return server.NOT_DONE_YET

    def runProcess(self, env, request, qargs=[]):
        """
        Run the cgi script.

        @type env: A L{dict} of L{str}, or L{None}
        @param env: The environment variables to pass to the process that will
            get spawned. See
            L{twisted.internet.interfaces.IReactorProcess.spawnProcess} for
            more information about environments and process creation.

        @type request: L{twisted.web.http.Request}
        @param request: An HTTP request.

        @type qargs: A L{list} of L{str}
        @param qargs: The command line arguments to pass to the process that
            will get spawned.
        """
        p = CGIProcessProtocol(request)
        self._reactor.spawnProcess(
            p,
            self.filename,
            [self.filename] + qargs,
            env,
            os.path.dirname(self.filename),
        )


class FilteredScript(CGIScript):
    """
    I am a special version of a CGI script, that uses a specific executable.

    This is useful for interfacing with other scripting languages that adhere
    to the CGI standard. My C{filter} attribute specifies what executable to
    run, and my C{filename} init parameter describes which script to pass to
    the first argument of that script.

    To customize me for a particular location of a CGI interpreter, override
    C{filter}.

    @type filter: L{str}
    @ivar filter: The absolute path to the executable.
    """

    filter = "/usr/bin/cat"

    def runProcess(self, env, request, qargs=[]):
        """
        Run a script through the C{filter} executable.

        @type env: A L{dict} of L{str}, or L{None}
        @param env: The environment variables to pass to the process that will
            get spawned. See
            L{twisted.internet.interfaces.IReactorProcess.spawnProcess}
            for more information about environments and process creation.

        @type request: L{twisted.web.http.Request}
        @param request: An HTTP request.

        @type qargs: A L{list} of L{str}
        @param qargs: The command line arguments to pass to the process that
            will get spawned.
        """
        p = CGIProcessProtocol(request)
        self._reactor.spawnProcess(
            p,
            self.filter,
            [self.filter, self.filename] + qargs,
            env,
            os.path.dirname(self.filename),
        )


class CGIProcessProtocol(protocol.ProcessProtocol, pb.Viewable):
    handling_headers = 1
    headers_written = 0
    headertext = b""
    errortext = b""
    _log = Logger()
    _requestFinished = False

    # Remotely relay producer interface.

    def view_resumeProducing(self, issuer):
        self.resumeProducing()

    def view_pauseProducing(self, issuer):
        self.pauseProducing()

    def view_stopProducing(self, issuer):
        self.stopProducing()

    def resumeProducing(self):
        self.transport.resumeProducing()

    def pauseProducing(self):
        self.transport.pauseProducing()

    def stopProducing(self):
        self.transport.loseConnection()

    def __init__(self, request):
        self.request = request
        self.request.notifyFinish().addBoth(self._finished)

    def connectionMade(self):
        self.request.registerProducer(self, 1)
        self.request.content.seek(0, 0)
        content = self.request.content.read()
        if content:
            self.transport.write(content)
        self.transport.closeStdin()

    def errReceived(self, error):
        self.errortext = self.errortext + error

    def outReceived(self, output):
        """
        Handle a chunk of input
        """
        # First, make sure that the headers from the script are sorted
        # out (we'll want to do some parsing on these later.)
        if self.handling_headers:
            text = self.headertext + output
            headerEnds = []
            for delimiter in b"\n\n", b"\r\n\r\n", b"\r\r", b"\n\r\n":
                headerend = text.find(delimiter)
                if headerend != -1:
                    headerEnds.append((headerend, delimiter))
            if headerEnds:
                # The script is entirely in control of response headers;
                # disable the default Content-Type value normally provided by
                # twisted.web.server.Request.
                self.request.defaultContentType = None

                headerEnds.sort()
                headerend, delimiter = headerEnds[0]
                self.headertext = text[:headerend]
                # This is a final version of the header text.
                linebreak = delimiter[: len(delimiter) // 2]
                headers = self.headertext.split(linebreak)
                for header in headers:
                    br = header.find(b": ")
                    if br == -1:
                        self._log.error(
                            "ignoring malformed CGI header: {header!r}", header=header
                        )
                    else:
                        headerName = header[:br].lower()
                        headerText = header[br + 2 :]
                        if headerName == b"location":
                            self.request.setResponseCode(http.FOUND)
                        if headerName == b"status":
                            try:
                                # "XXX <description>" sometimes happens.
                                statusNum = int(headerText[:3])
                            except BaseException:
                                self._log.error("malformed status header")
                            else:
                                self.request.setResponseCode(statusNum)
                        else:
                            # Don't allow the application to control
                            # these required headers.
                            if headerName.lower() not in (b"server", b"date"):
                                self.request.responseHeaders.addRawHeader(
                                    headerName, headerText
                                )
                output = text[headerend + len(delimiter) :]
                self.handling_headers = 0
            if self.handling_headers:
                self.headertext = text
        if not self.handling_headers:
            self.request.write(output)

    def processEnded(self, reason):
        if reason.value.exitCode != 0:
            self._log.error(
                "CGI {uri} exited with exit code {exitCode}",
                uri=self.request.uri,
                exitCode=reason.value.exitCode,
            )
        if self.errortext:
            self._log.error(
                "Errors from CGI {uri}: {errorText}",
                uri=self.request.uri,
                errorText=self.errortext,
            )

        if self.handling_headers:
            self._log.error(
                "Premature end of headers in {uri}: {headerText}",
                uri=self.request.uri,
                headerText=self.headertext,
            )
            if not self._requestFinished:
                self.request.write(
                    resource.ErrorPage(
                        http.INTERNAL_SERVER_ERROR,
                        "CGI Script Error",
                        "Premature end of script headers.",
                    ).render(self.request)
                )

        if not self._requestFinished:
            self.request.unregisterProducer()
            self.request.finish()

    def _finished(self, ignored):
        """
        Record the end of the response generation for the request being
        serviced.
        """
        self._requestFinished = True
