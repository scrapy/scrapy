# -*- test-case-name: twisted.web.test.test_util -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
An assortment of web server-related utilities.
"""

from __future__ import division, absolute_import

import linecache

from twisted.python import urlpath
from twisted.python.compat import _PY3, unicode, nativeString, escape
from twisted.python.reflect import fullyQualifiedName

from twisted.web import resource

from twisted.web.template import TagLoader, XMLString, Element, renderer
from twisted.web.template import flattenString



def _PRE(text):
    """
    Wraps <pre> tags around some text and HTML-escape it.

    This is here since once twisted.web.html was deprecated it was hard to
    migrate the html.PRE from current code to twisted.web.template.

    For new code consider using twisted.web.template.

    @return: Escaped text wrapped in <pre> tags.
    @rtype: C{str}
    """
    return '<pre>%s</pre>' % (escape(text),)



def redirectTo(URL, request):
    """
    Generate a redirect to the given location.

    @param URL: A L{bytes} giving the location to which to redirect.
    @type URL: L{bytes}

    @param request: The request object to use to generate the redirect.
    @type request: L{IRequest<twisted.web.iweb.IRequest>} provider

    @raise TypeError: If the type of C{URL} a L{unicode} instead of L{bytes}.

    @return: A C{bytes} containing HTML which tries to convince the client agent
        to visit the new location even if it doesn't respect the I{FOUND}
        response code.  This is intended to be returned from a render method,
        eg::

            def render_GET(self, request):
                return redirectTo(b"http://example.com/", request)
    """
    if isinstance(URL, unicode) :
        raise TypeError("Unicode object not allowed as URL")
    request.setHeader(b"Content-Type", b"text/html; charset=utf-8")
    request.redirect(URL)
    content =  """
<html>
    <head>
        <meta http-equiv=\"refresh\" content=\"0;URL=%(url)s\">
    </head>
    <body bgcolor=\"#FFFFFF\" text=\"#000000\">
    <a href=\"%(url)s\">click here</a>
    </body>
</html>
""" % {'url': nativeString(URL)}
    if _PY3:
        content = content.encode("utf8")
    return content


class Redirect(resource.Resource):
    isLeaf = True

    def __init__(self, url):
        resource.Resource.__init__(self)
        self.url = url

    def render(self, request):
        return redirectTo(self.url, request)

    def getChild(self, name, request):
        return self


class ChildRedirector(Redirect):
    isLeaf = 0
    def __init__(self, url):
        # XXX is this enough?
        if ((url.find('://') == -1)
            and (not url.startswith('..'))
            and (not url.startswith('/'))):
            raise ValueError("It seems you've given me a redirect (%s) that is a child of myself! That's not good, it'll cause an infinite redirect." % url)
        Redirect.__init__(self, url)

    def getChild(self, name, request):
        newUrl = self.url
        if not newUrl.endswith('/'):
            newUrl += '/'
        newUrl += name
        return ChildRedirector(newUrl)


class ParentRedirect(resource.Resource):
    """
    I redirect to URLPath.here().
    """
    isLeaf = 1
    def render(self, request):
        return redirectTo(urlpath.URLPath.fromRequest(request).here(), request)

    def getChild(self, request):
        return self


class DeferredResource(resource.Resource):
    """
    I wrap up a Deferred that will eventually result in a Resource
    object.
    """
    isLeaf = 1

    def __init__(self, d):
        resource.Resource.__init__(self)
        self.d = d

    def getChild(self, name, request):
        return self

    def render(self, request):
        self.d.addCallback(self._cbChild, request).addErrback(
            self._ebChild,request)
        from twisted.web.server import NOT_DONE_YET
        return NOT_DONE_YET

    def _cbChild(self, child, request):
        request.render(resource.getChildForRequest(child, request))

    def _ebChild(self, reason, request):
        request.processingFailed(reason)



class _SourceLineElement(Element):
    """
    L{_SourceLineElement} is an L{IRenderable} which can render a single line of
    source code.

    @ivar number: A C{int} giving the line number of the source code to be
        rendered.
    @ivar source: A C{str} giving the source code to be rendered.
    """
    def __init__(self, loader, number, source):
        Element.__init__(self, loader)
        self.number = number
        self.source = source


    @renderer
    def sourceLine(self, request, tag):
        """
        Render the line of source as a child of C{tag}.
        """
        return tag(self.source.replace('  ', u' \N{NO-BREAK SPACE}'))


    @renderer
    def lineNumber(self, request, tag):
        """
        Render the line number as a child of C{tag}.
        """
        return tag(str(self.number))



class _SourceFragmentElement(Element):
    """
    L{_SourceFragmentElement} is an L{IRenderable} which can render several lines
    of source code near the line number of a particular frame object.

    @ivar frame: A L{Failure<twisted.python.failure.Failure>}-style frame object
        for which to load a source line to render.  This is really a tuple
        holding some information from a frame object.  See
        L{Failure.frames<twisted.python.failure.Failure>} for specifics.
    """
    def __init__(self, loader, frame):
        Element.__init__(self, loader)
        self.frame = frame


    def _getSourceLines(self):
        """
        Find the source line references by C{self.frame} and yield, in source
        line order, it and the previous and following lines.

        @return: A generator which yields two-tuples.  Each tuple gives a source
            line number and the contents of that source line.
        """
        filename = self.frame[1]
        lineNumber = self.frame[2]
        for snipLineNumber in range(lineNumber - 1, lineNumber + 2):
            yield (snipLineNumber,
                   linecache.getline(filename, snipLineNumber).rstrip())


    @renderer
    def sourceLines(self, request, tag):
        """
        Render the source line indicated by C{self.frame} and several
        surrounding lines.  The active line will be given a I{class} of
        C{"snippetHighlightLine"}.  Other lines will be given a I{class} of
        C{"snippetLine"}.
        """
        for (lineNumber, sourceLine) in self._getSourceLines():
            newTag = tag.clone()
            if lineNumber == self.frame[2]:
                cssClass = "snippetHighlightLine"
            else:
                cssClass = "snippetLine"
            loader = TagLoader(newTag(**{"class": cssClass}))
            yield _SourceLineElement(loader, lineNumber, sourceLine)



class _FrameElement(Element):
    """
    L{_FrameElement} is an L{IRenderable} which can render details about one
    frame from a L{Failure<twisted.python.failure.Failure>}.

    @ivar frame: A L{Failure<twisted.python.failure.Failure>}-style frame object
        for which to load a source line to render.  This is really a tuple
        holding some information from a frame object.  See
        L{Failure.frames<twisted.python.failure.Failure>} for specifics.
    """
    def __init__(self, loader, frame):
        Element.__init__(self, loader)
        self.frame = frame


    @renderer
    def filename(self, request, tag):
        """
        Render the name of the file this frame references as a child of C{tag}.
        """
        return tag(self.frame[1])


    @renderer
    def lineNumber(self, request, tag):
        """
        Render the source line number this frame references as a child of
        C{tag}.
        """
        return tag(str(self.frame[2]))


    @renderer
    def function(self, request, tag):
        """
        Render the function name this frame references as a child of C{tag}.
        """
        return tag(self.frame[0])


    @renderer
    def source(self, request, tag):
        """
        Render the source code surrounding the line this frame references,
        replacing C{tag}.
        """
        return _SourceFragmentElement(TagLoader(tag), self.frame)



class _StackElement(Element):
    """
    L{_StackElement} renders an L{IRenderable} which can render a list of frames.
    """
    def __init__(self, loader, stackFrames):
        Element.__init__(self, loader)
        self.stackFrames = stackFrames


    @renderer
    def frames(self, request, tag):
        """
        Render the list of frames in this L{_StackElement}, replacing C{tag}.
        """
        return [
            _FrameElement(TagLoader(tag.clone()), frame)
            for frame
            in self.stackFrames]



class FailureElement(Element):
    """
    L{FailureElement} is an L{IRenderable} which can render detailed information
    about a L{Failure<twisted.python.failure.Failure>}.

    @ivar failure: The L{Failure<twisted.python.failure.Failure>} instance which
        will be rendered.

    @since: 12.1
    """
    loader = XMLString("""
<div xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1">
  <style type="text/css">
    div.error {
      color: red;
      font-family: Verdana, Arial, helvetica, sans-serif;
      font-weight: bold;
    }

    div {
      font-family: Verdana, Arial, helvetica, sans-serif;
    }

    div.stackTrace {
    }

    div.frame {
      padding: 1em;
      background: white;
      border-bottom: thin black dashed;
    }

    div.frame:first-child {
      padding: 1em;
      background: white;
      border-top: thin black dashed;
      border-bottom: thin black dashed;
    }

    div.location {
    }

    span.function {
      font-weight: bold;
      font-family: "Courier New", courier, monospace;
    }

    div.snippet {
      margin-bottom: 0.5em;
      margin-left: 1em;
      background: #FFFFDD;
    }

    div.snippetHighlightLine {
      color: red;
    }

    span.code {
      font-family: "Courier New", courier, monospace;
    }
  </style>

  <div class="error">
    <span t:render="type" />: <span t:render="value" />
  </div>
  <div class="stackTrace" t:render="traceback">
    <div class="frame" t:render="frames">
      <div class="location">
        <span t:render="filename" />:<span t:render="lineNumber" /> in
        <span class="function" t:render="function" />
      </div>
      <div class="snippet" t:render="source">
        <div t:render="sourceLines">
          <span class="lineno" t:render="lineNumber" />
          <code class="code" t:render="sourceLine" />
        </div>
      </div>
    </div>
  </div>
  <div class="error">
    <span t:render="type" />: <span t:render="value" />
  </div>
</div>
""")

    def __init__(self, failure, loader=None):
        Element.__init__(self, loader)
        self.failure = failure


    @renderer
    def type(self, request, tag):
        """
        Render the exception type as a child of C{tag}.
        """
        return tag(fullyQualifiedName(self.failure.type))


    @renderer
    def value(self, request, tag):
        """
        Render the exception value as a child of C{tag}.
        """
        return tag(unicode(self.failure.value).encode('utf8'))


    @renderer
    def traceback(self, request, tag):
        """
        Render all the frames in the wrapped
        L{Failure<twisted.python.failure.Failure>}'s traceback stack, replacing
        C{tag}.
        """
        return _StackElement(TagLoader(tag), self.failure.frames)



def formatFailure(myFailure):
    """
    Construct an HTML representation of the given failure.

    Consider using L{FailureElement} instead.

    @type myFailure: L{Failure<twisted.python.failure.Failure>}

    @rtype: C{bytes}
    @return: A string containing the HTML representation of the given failure.
    """
    result = []
    flattenString(None, FailureElement(myFailure)).addBoth(result.append)
    if isinstance(result[0], bytes):
        # Ensure the result string is all ASCII, for compatibility with the
        # default encoding expected by browsers.
        return result[0].decode('utf-8').encode('ascii', 'xmlcharrefreplace')
    result[0].raiseException()



__all__ = [
    "redirectTo", "Redirect", "ChildRedirector", "ParentRedirect",
    "DeferredResource", "FailureElement", "formatFailure"]
