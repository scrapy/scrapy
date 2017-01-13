# -*- test-case-name: twisted.web.test.test_script -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
I contain PythonScript, which is a very simple python script resource.
"""

from __future__ import division, absolute_import

import os, traceback

from twisted import copyright
from twisted.python.filepath import _coerceToFilesystemEncoding
from twisted.python.compat import execfile, networkString, NativeStringIO, _PY3
from twisted.web import http, server, static, resource, util


rpyNoResource = """<p>You forgot to assign to the variable "resource" in your script. For example:</p>
<pre>
# MyCoolWebApp.rpy

import mygreatresource

resource = mygreatresource.MyGreatResource()
</pre>
"""

class AlreadyCached(Exception):
    """
    This exception is raised when a path has already been cached.
    """

class CacheScanner:
    def __init__(self, path, registry):
        self.path = path
        self.registry = registry
        self.doCache = 0

    def cache(self):
        c = self.registry.getCachedPath(self.path)
        if c is not None:
            raise AlreadyCached(c)
        self.recache()

    def recache(self):
        self.doCache = 1

noRsrc = resource.ErrorPage(500, "Whoops! Internal Error", rpyNoResource)

def ResourceScript(path, registry):
    """
    I am a normal py file which must define a 'resource' global, which should
    be an instance of (a subclass of) web.resource.Resource; it will be
    renderred.
    """
    cs = CacheScanner(path, registry)
    glob = {'__file__': _coerceToFilesystemEncoding("", path),
            'resource': noRsrc,
            'registry': registry,
            'cache': cs.cache,
            'recache': cs.recache}
    try:
        execfile(path, glob, glob)
    except AlreadyCached as ac:
        return ac.args[0]
    rsrc = glob['resource']
    if cs.doCache and rsrc is not noRsrc:
        registry.cachePath(path, rsrc)
    return rsrc



def ResourceTemplate(path, registry):
    from quixote import ptl_compile

    glob = {'__file__': _coerceToFilesystemEncoding("", path),
            'resource': resource.ErrorPage(500, "Whoops! Internal Error",
                                           rpyNoResource),
            'registry': registry}

    with open(path) as f:  # Not closed by quixote as of 2.9.1
        e = ptl_compile.compile_template(f, path)
    code = compile(e, "<source>", "exec")
    eval(code, glob, glob)
    return glob['resource']



class ResourceScriptWrapper(resource.Resource):

    def __init__(self, path, registry=None):
        resource.Resource.__init__(self)
        self.path = path
        self.registry = registry or static.Registry()

    def render(self, request):
        res = ResourceScript(self.path, self.registry)
        return res.render(request)

    def getChildWithDefault(self, path, request):
        res = ResourceScript(self.path, self.registry)
        return res.getChildWithDefault(path, request)



class ResourceScriptDirectory(resource.Resource):
    """
    L{ResourceScriptDirectory} is a resource which serves scripts from a
    filesystem directory.  File children of a L{ResourceScriptDirectory} will
    be served using L{ResourceScript}.  Directory children will be served using
    another L{ResourceScriptDirectory}.

    @ivar path: A C{str} giving the filesystem path in which children will be
        looked up.

    @ivar registry: A L{static.Registry} instance which will be used to decide
        how to interpret scripts found as children of this resource.
    """
    def __init__(self, pathname, registry=None):
        resource.Resource.__init__(self)
        self.path = pathname
        self.registry = registry or static.Registry()

    def getChild(self, path, request):
        fn = os.path.join(self.path, path)

        if os.path.isdir(fn):
            return ResourceScriptDirectory(fn, self.registry)
        if os.path.exists(fn):
            return ResourceScript(fn, self.registry)
        return resource.NoResource()

    def render(self, request):
        return resource.NoResource().render(request)



class PythonScript(resource.Resource):
    """
    I am an extremely simple dynamic resource; an embedded python script.

    This will execute a file (usually of the extension '.epy') as Python code,
    internal to the webserver.
    """
    isLeaf = True

    def __init__(self, filename, registry):
        """
        Initialize me with a script name.
        """
        self.filename = filename
        self.registry = registry

    def render(self, request):
        """
        Render me to a web client.

        Load my file, execute it in a special namespace (with 'request' and
        '__file__' global vars) and finish the request.  Output to the web-page
        will NOT be handled with print - standard output goes to the log - but
        with request.write.
        """
        request.setHeader(b"x-powered-by", networkString("Twisted/%s" % copyright.version))
        namespace = {'request': request,
                     '__file__': _coerceToFilesystemEncoding("", self.filename),
                     'registry': self.registry}
        try:
            execfile(self.filename, namespace, namespace)
        except IOError as e:
            if e.errno == 2: #file not found
                request.setResponseCode(http.NOT_FOUND)
                request.write(resource.NoResource("File not found.").render(request))
        except:
            io = NativeStringIO()
            traceback.print_exc(file=io)
            output = util._PRE(io.getvalue())
            if _PY3:
                output = output.encode("utf8")
            request.write(output)
        request.finish()
        return server.NOT_DONE_YET
