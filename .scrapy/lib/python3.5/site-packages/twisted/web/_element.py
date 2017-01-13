# -*- test-case-name: twisted.web.test.test_template -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

from __future__ import division, absolute_import

from zope.interface import implementer

from twisted.web.iweb import IRenderable
from twisted.web.error import MissingRenderMethod, UnexposedMethodError
from twisted.web.error import MissingTemplateLoader


class Expose(object):
    """
    Helper for exposing methods for various uses using a simple decorator-style
    callable.

    Instances of this class can be called with one or more functions as
    positional arguments.  The names of these functions will be added to a list
    on the class object of which they are methods.

    @ivar attributeName: The attribute with which exposed methods will be
    tracked.
    """
    def __init__(self, doc=None):
        self.doc = doc


    def __call__(self, *funcObjs):
        """
        Add one or more functions to the set of exposed functions.

        This is a way to declare something about a class definition, similar to
        L{zope.interface.declarations.implementer}.  Use it like this::

            magic = Expose('perform extra magic')
            class Foo(Bar):
                def twiddle(self, x, y):
                    ...
                def frob(self, a, b):
                    ...
                magic(twiddle, frob)

        Later you can query the object::

            aFoo = Foo()
            magic.get(aFoo, 'twiddle')(x=1, y=2)

        The call to C{get} will fail if the name it is given has not been
        exposed using C{magic}.

        @param funcObjs: One or more function objects which will be exposed to
        the client.

        @return: The first of C{funcObjs}.
        """
        if not funcObjs:
            raise TypeError("expose() takes at least 1 argument (0 given)")
        for fObj in funcObjs:
            fObj.exposedThrough = getattr(fObj, 'exposedThrough', [])
            fObj.exposedThrough.append(self)
        return funcObjs[0]


    _nodefault = object()
    def get(self, instance, methodName, default=_nodefault):
        """
        Retrieve an exposed method with the given name from the given instance.

        @raise UnexposedMethodError: Raised if C{default} is not specified and
        there is no exposed method with the given name.

        @return: A callable object for the named method assigned to the given
        instance.
        """
        method = getattr(instance, methodName, None)
        exposedThrough = getattr(method, 'exposedThrough', [])
        if self not in exposedThrough:
            if default is self._nodefault:
                raise UnexposedMethodError(self, methodName)
            return default
        return method


    @classmethod
    def _withDocumentation(cls, thunk):
        """
        Slight hack to make users of this class appear to have a docstring to
        documentation generators, by defining them with a decorator.  (This hack
        should be removed when epydoc can be convinced to use some other method
        for documenting.)
        """
        return cls(thunk.__doc__)


# Avoid exposing the ugly, private classmethod name in the docs.  Luckily this
# namespace is private already so this doesn't leak further.
exposer = Expose._withDocumentation

@exposer
def renderer():
    """
    Decorate with L{renderer} to use methods as template render directives.

    For example::

        class Foo(Element):
            @renderer
            def twiddle(self, request, tag):
                return tag('Hello, world.')

        <div xmlns:t="http://twistedmatrix.com/ns/twisted.web.template/0.1">
            <span t:render="twiddle" />
        </div>

    Will result in this final output::

        <div>
            <span>Hello, world.</span>
        </div>
    """



@implementer(IRenderable)
class Element(object):
    """
    Base for classes which can render part of a page.

    An Element is a renderer that can be embedded in a stan document and can
    hook its template (from the loader) up to render methods.

    An Element might be used to encapsulate the rendering of a complex piece of
    data which is to be displayed in multiple different contexts.  The Element
    allows the rendering logic to be easily re-used in different ways.

    Element returns render methods which are registered using
    L{twisted.web._element.renderer}.  For example::

        class Menu(Element):
            @renderer
            def items(self, request, tag):
                ....

    Render methods are invoked with two arguments: first, the
    L{twisted.web.http.Request} being served and second, the tag object which
    "invoked" the render method.

    @type loader: L{ITemplateLoader} provider
    @ivar loader: The factory which will be used to load documents to
        return from C{render}.
    """
    loader = None

    def __init__(self, loader=None):
        if loader is not None:
            self.loader = loader


    def lookupRenderMethod(self, name):
        """
        Look up and return the named render method.
        """
        method = renderer.get(self, name, None)
        if method is None:
            raise MissingRenderMethod(self, name)
        return method


    def render(self, request):
        """
        Implement L{IRenderable} to allow one L{Element} to be embedded in
        another's template or rendering output.

        (This will simply load the template from the C{loader}; when used in a
        template, the flattening engine will keep track of this object
        separately as the object to lookup renderers on and call
        L{Element.renderer} to look them up.  The resulting object from this
        method is not directly associated with this L{Element}.)
        """
        loader = self.loader
        if loader is None:
            raise MissingTemplateLoader(self)
        return loader.load()
