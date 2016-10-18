# -*- test-case-name: twisted.web.
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
I am a virtual hosts implementation.
"""

from __future__ import division, absolute_import

# Twisted Imports
from twisted.python import roots
from twisted.web import resource


class VirtualHostCollection(roots.Homogenous):
    """Wrapper for virtual hosts collection.

    This exists for configuration purposes.
    """
    entityType = resource.Resource

    def __init__(self, nvh):
        self.nvh = nvh

    def listStaticEntities(self):
        return self.nvh.hosts.items()

    def getStaticEntity(self, name):
        return self.nvh.hosts.get(self)

    def reallyPutEntity(self, name, entity):
        self.nvh.addHost(name, entity)

    def delEntity(self, name):
        self.nvh.removeHost(name)


class NameVirtualHost(resource.Resource):
    """I am a resource which represents named virtual hosts.
    """

    default = None

    def __init__(self):
        """Initialize.
        """
        resource.Resource.__init__(self)
        self.hosts = {}

    def listStaticEntities(self):
        return resource.Resource.listStaticEntities(self) + [("Virtual Hosts", VirtualHostCollection(self))]

    def getStaticEntity(self, name):
        if name == "Virtual Hosts":
            return VirtualHostCollection(self)
        else:
            return resource.Resource.getStaticEntity(self, name)

    def addHost(self, name, resrc):
        """Add a host to this virtual host.

        This will take a host named `name', and map it to a resource
        `resrc'.  For example, a setup for our virtual hosts would be::

            nvh.addHost('divunal.com', divunalDirectory)
            nvh.addHost('www.divunal.com', divunalDirectory)
            nvh.addHost('twistedmatrix.com', twistedMatrixDirectory)
            nvh.addHost('www.twistedmatrix.com', twistedMatrixDirectory)
        """
        self.hosts[name] = resrc

    def removeHost(self, name):
        """Remove a host."""
        del self.hosts[name]

    def _getResourceForRequest(self, request):
        """(Internal) Get the appropriate resource for the given host.
        """
        hostHeader = request.getHeader(b'host')
        if hostHeader == None:
            return self.default or resource.NoResource()
        else:
            host = hostHeader.lower().split(b':', 1)[0]
        return (self.hosts.get(host, self.default)
                or resource.NoResource("host %s not in vhost map" % repr(host)))

    def render(self, request):
        """Implementation of resource.Resource's render method.
        """
        resrc = self._getResourceForRequest(request)
        return resrc.render(request)

    def getChild(self, path, request):
        """Implementation of resource.Resource's getChild method.
        """
        resrc = self._getResourceForRequest(request)
        if resrc.isLeaf:
            request.postpath.insert(0,request.prepath.pop(-1))
            return resrc
        else:
            return resrc.getChildWithDefault(path, request)

class _HostResource(resource.Resource):

    def getChild(self, path, request):
        if b':' in path:
            host, port = path.split(b':', 1)
            port = int(port)
        else:
            host, port = path, 80
        request.setHost(host, port)
        prefixLen = (3 + request.isSecure() + 4 + len(path) +
                     len(request.prepath[-3]))
        request.path = b'/' + b'/'.join(request.postpath)
        request.uri = request.uri[prefixLen:]
        del request.prepath[:3]
        return request.site.getResourceFor(request)


class VHostMonsterResource(resource.Resource):

    """
    Use this to be able to record the hostname and method (http vs. https)
    in the URL without disturbing your web site. If you put this resource
    in a URL http://foo.com/bar then requests to
    http://foo.com/bar/http/baz.com/something will be equivalent to
    http://foo.com/something, except that the hostname the request will
    appear to be accessing will be "baz.com". So if "baz.com" is redirecting
    all requests for to foo.com, while foo.com is inaccessible from the outside,
    then redirect and url generation will work correctly
    """
    def getChild(self, path, request):
        if path == b'http':
            request.isSecure = lambda: 0
        elif path == b'https':
            request.isSecure = lambda: 1
        return _HostResource()
