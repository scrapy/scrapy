# -*- test-case-name: twisted.python.test.test_deprecate -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Deprecation framework for Twisted.

To mark a method, function, or class as being deprecated do this::

    from twisted.python.versions import Version
    from twisted.python.deprecate import deprecated

    @deprecated(Version("Twisted", 8, 0, 0))
    def badAPI(self, first, second):
        '''
        Docstring for badAPI.
        '''
        ...

    @deprecated(Version("Twisted", 16, 0, 0))
    class BadClass(object):
        '''
        Docstring for BadClass.
        '''

The newly-decorated badAPI will issue a warning when called, and BadClass will
issue a warning when instantiated. Both will also have  a deprecation notice
appended to their docstring.

To deprecate properties you can use::

    from twisted.python.versions import Version
    from twisted.python.deprecate import deprecatedProperty

    class OtherwiseUndeprecatedClass(object):

        @deprecatedProperty(Version('Twisted', 16, 0, 0))
        def badProperty(self):
            '''
            Docstring for badProperty.
            '''

        @badProperty.setter
        def badProperty(self, value):
            '''
            Setter sill also raise the deprecation warning.
            '''


To mark module-level attributes as being deprecated you can use::

    badAttribute = "someValue"

    ...

    deprecatedModuleAttribute(
        Version("Twisted", 8, 0, 0),
        "Use goodAttribute instead.",
        "your.full.module.name",
        "badAttribute")

The deprecated attributes will issue a warning whenever they are accessed. If
the attributes being deprecated are in the same module as the
L{deprecatedModuleAttribute} call is being made from, the C{__name__} global
can be used as the C{moduleName} parameter.

See also L{Version}.

@type DEPRECATION_WARNING_FORMAT: C{str}
@var DEPRECATION_WARNING_FORMAT: The default deprecation warning string format
    to use when one is not provided by the user.
"""

from __future__ import division, absolute_import

__all__ = [
    'deprecated',
    'deprecatedProperty',
    'getDeprecationWarningString',
    'getWarningMethod',
    'setWarningMethod',
    'deprecatedModuleAttribute',
    ]


import sys, inspect
from warnings import warn, warn_explicit
from dis import findlinestarts
from functools import wraps

from twisted.python.versions import getVersionString
from twisted.python.compat import _PY3

DEPRECATION_WARNING_FORMAT = '%(fqpn)s was deprecated in %(version)s'

# Notionally, part of twisted.python.reflect, but defining it there causes a
# cyclic dependency between this module and that module.  Define it here,
# instead, and let reflect import it to re-expose to the public.
def _fullyQualifiedName(obj):
    """
    Return the fully qualified name of a module, class, method or function.
    Classes and functions need to be module level ones to be correctly
    qualified.

    @rtype: C{str}.
    """
    try:
        name = obj.__qualname__
    except AttributeError:
        name = obj.__name__

    if inspect.isclass(obj) or inspect.isfunction(obj):
        moduleName = obj.__module__
        return "%s.%s" % (moduleName, name)
    elif inspect.ismethod(obj):
        try:
            cls = obj.im_class
        except AttributeError:
            # Python 3 eliminates im_class, substitutes __module__ and
            # __qualname__ to provide similar information.
            return "%s.%s" % (obj.__module__, obj.__qualname__)
        else:
            className = _fullyQualifiedName(cls)
            return "%s.%s" % (className, name)
    return name
# Try to keep it looking like something in twisted.python.reflect.
_fullyQualifiedName.__module__ = 'twisted.python.reflect'
_fullyQualifiedName.__name__ = 'fullyQualifiedName'
_fullyQualifiedName.__qualname__ = 'fullyQualifiedName'


def _getReplacementString(replacement):
    """
    Surround a replacement for a deprecated API with some polite text exhorting
    the user to consider it as an alternative.

    @type replacement: C{str} or callable

    @return: a string like "please use twisted.python.modules.getModule
        instead".
    """
    if callable(replacement):
        replacement = _fullyQualifiedName(replacement)
    return "please use %s instead" % (replacement,)



def _getDeprecationDocstring(version, replacement=None):
    """
    Generate an addition to a deprecated object's docstring that explains its
    deprecation.

    @param version: the version it was deprecated.
    @type version: L{Version}

    @param replacement: The replacement, if specified.
    @type replacement: C{str} or callable

    @return: a string like "Deprecated in Twisted 27.2.0; please use
        twisted.timestream.tachyon.flux instead."
    """
    doc = "Deprecated in %s" % (getVersionString(version),)
    if replacement:
        doc = "%s; %s" % (doc, _getReplacementString(replacement))
    return doc + "."



def _getDeprecationWarningString(fqpn, version, format=None, replacement=None):
    """
    Return a string indicating that the Python name was deprecated in the given
    version.

    @param fqpn: Fully qualified Python name of the thing being deprecated
    @type fqpn: C{str}

    @param version: Version that C{fqpn} was deprecated in.
    @type version: L{twisted.python.versions.Version}

    @param format: A user-provided format to interpolate warning values into, or
        L{DEPRECATION_WARNING_FORMAT
        <twisted.python.deprecate.DEPRECATION_WARNING_FORMAT>} if L{None} is
        given.
    @type format: C{str}

    @param replacement: what should be used in place of C{fqpn}. Either pass in
        a string, which will be inserted into the warning message, or a
        callable, which will be expanded to its full import path.
    @type replacement: C{str} or callable

    @return: A textual description of the deprecation
    @rtype: C{str}
    """
    if format is None:
        format = DEPRECATION_WARNING_FORMAT
    warningString = format % {
        'fqpn': fqpn,
        'version': getVersionString(version)}
    if replacement:
        warningString = "%s; %s" % (
            warningString, _getReplacementString(replacement))
    return warningString



def getDeprecationWarningString(callableThing, version, format=None,
                                replacement=None):
    """
    Return a string indicating that the callable was deprecated in the given
    version.

    @type callableThing: C{callable}
    @param callableThing: Callable object to be deprecated

    @type version: L{twisted.python.versions.Version}
    @param version: Version that C{callableThing} was deprecated in

    @type format: C{str}
    @param format: A user-provided format to interpolate warning values into,
        or L{DEPRECATION_WARNING_FORMAT
        <twisted.python.deprecate.DEPRECATION_WARNING_FORMAT>} if L{None} is
        given

    @param callableThing: A callable to be deprecated.

    @param version: The L{twisted.python.versions.Version} that the callable
        was deprecated in.

    @param replacement: what should be used in place of the callable. Either
        pass in a string, which will be inserted into the warning message,
        or a callable, which will be expanded to its full import path.
    @type replacement: C{str} or callable

    @return: A string describing the deprecation.
    @rtype: C{str}
    """
    return _getDeprecationWarningString(
        _fullyQualifiedName(callableThing), version, format, replacement)



def _appendToDocstring(thingWithDoc, textToAppend):
    """
    Append the given text to the docstring of C{thingWithDoc}.

    If C{thingWithDoc} has no docstring, then the text just replaces the
    docstring. If it has a single-line docstring then it appends a blank line
    and the message text. If it has a multi-line docstring, then in appends a
    blank line a the message text, and also does the indentation correctly.
    """
    if thingWithDoc.__doc__:
        docstringLines = thingWithDoc.__doc__.splitlines()
    else:
        docstringLines = []

    if len(docstringLines) == 0:
        docstringLines.append(textToAppend)
    elif len(docstringLines) == 1:
        docstringLines.extend(['', textToAppend, ''])
    else:
        spaces = docstringLines.pop()
        docstringLines.extend(['',
                               spaces + textToAppend,
                               spaces])
    thingWithDoc.__doc__ = '\n'.join(docstringLines)



def deprecated(version, replacement=None):
    """
    Return a decorator that marks callables as deprecated. To deprecate a
    property, see L{deprecatedProperty}.

    @type version: L{twisted.python.versions.Version}
    @param version: The version in which the callable will be marked as
        having been deprecated.  The decorated function will be annotated
        with this version, having it set as its C{deprecatedVersion}
        attribute.

    @param version: the version that the callable was deprecated in.
    @type version: L{twisted.python.versions.Version}

    @param replacement: what should be used in place of the callable. Either
        pass in a string, which will be inserted into the warning message,
        or a callable, which will be expanded to its full import path.
    @type replacement: C{str} or callable
    """
    def deprecationDecorator(function):
        """
        Decorator that marks C{function} as deprecated.
        """
        warningString = getDeprecationWarningString(
            function, version, None, replacement)

        @wraps(function)
        def deprecatedFunction(*args, **kwargs):
            warn(
                warningString,
                DeprecationWarning,
                stacklevel=2)
            return function(*args, **kwargs)

        _appendToDocstring(deprecatedFunction,
                           _getDeprecationDocstring(version, replacement))
        deprecatedFunction.deprecatedVersion = version
        return deprecatedFunction

    return deprecationDecorator



def deprecatedProperty(version, replacement=None):
    """
    Return a decorator that marks a property as deprecated. To deprecate a
    regular callable or class, see L{deprecated}.

    @type version: L{twisted.python.versions.Version}
    @param version: The version in which the callable will be marked as
        having been deprecated.  The decorated function will be annotated
        with this version, having it set as its C{deprecatedVersion}
        attribute.

    @param version: the version that the callable was deprecated in.
    @type version: L{twisted.python.versions.Version}

    @param replacement: what should be used in place of the callable.
        Either pass in a string, which will be inserted into the warning
        message, or a callable, which will be expanded to its full import
        path.
    @type replacement: C{str} or callable

    @return: A new property with deprecated setter and getter.
    @rtype: C{property}

    @since: 16.1.0
    """

    class _DeprecatedProperty(property):
        """
        Extension of the build-in property to allow deprecated setters.
        """

        def _deprecatedWrapper(self, function):
            @wraps(function)
            def deprecatedFunction(*args, **kwargs):
                warn(
                    self.warningString,
                    DeprecationWarning,
                    stacklevel=2)
                return function(*args, **kwargs)
            return deprecatedFunction


        def setter(self, function):
            return property.setter(self, self._deprecatedWrapper(function))


    def deprecationDecorator(function):
        if _PY3:
            warningString = getDeprecationWarningString(
                function, version, None, replacement)
        else:
            # Because Python 2 sucks, we need to implement our own here -- lack
            # of __qualname__ means that we kinda have to stack walk. It maybe
            # probably works. Probably. -Amber
            functionName = function.__name__
            className = inspect.stack()[1][3]  # wow hax
            moduleName = function.__module__

            fqdn = "%s.%s.%s" % (moduleName, className, functionName)

            warningString = _getDeprecationWarningString(
                fqdn, version, None, replacement)

        @wraps(function)
        def deprecatedFunction(*args, **kwargs):
            warn(
                warningString,
                DeprecationWarning,
                stacklevel=2)
            return function(*args, **kwargs)

        _appendToDocstring(deprecatedFunction,
                           _getDeprecationDocstring(version, replacement))
        deprecatedFunction.deprecatedVersion = version

        result = _DeprecatedProperty(deprecatedFunction)
        result.warningString = warningString
        return result

    return deprecationDecorator



def getWarningMethod():
    """
    Return the warning method currently used to record deprecation warnings.
    """
    return warn



def setWarningMethod(newMethod):
    """
    Set the warning method to use to record deprecation warnings.

    The callable should take message, category and stacklevel. The return
    value is ignored.
    """
    global warn
    warn = newMethod



class _InternalState(object):
    """
    An L{_InternalState} is a helper object for a L{_ModuleProxy}, so that it
    can easily access its own attributes, bypassing its logic for delegating to
    another object that it's proxying for.

    @ivar proxy: a L{_ModuleProxy}
    """
    def __init__(self, proxy):
        object.__setattr__(self, 'proxy', proxy)


    def __getattribute__(self, name):
        return object.__getattribute__(object.__getattribute__(self, 'proxy'),
                                       name)


    def __setattr__(self, name, value):
        return object.__setattr__(object.__getattribute__(self, 'proxy'),
                                  name, value)



class _ModuleProxy(object):
    """
    Python module wrapper to hook module-level attribute access.

    Access to deprecated attributes first checks
    L{_ModuleProxy._deprecatedAttributes}, if the attribute does not appear
    there then access falls through to L{_ModuleProxy._module}, the wrapped
    module object.

    @ivar _module: Module on which to hook attribute access.
    @type _module: C{module}

    @ivar _deprecatedAttributes: Mapping of attribute names to objects that
        retrieve the module attribute's original value.
    @type _deprecatedAttributes: C{dict} mapping C{str} to
        L{_DeprecatedAttribute}

    @ivar _lastWasPath: Heuristic guess as to whether warnings about this
        package should be ignored for the next call.  If the last attribute
        access of this module was a C{getattr} of C{__path__}, we will assume
        that it was the import system doing it and we won't emit a warning for
        the next access, even if it is to a deprecated attribute.  The CPython
        import system always tries to access C{__path__}, then the attribute
        itself, then the attribute itself again, in both successful and failed
        cases.
    @type _lastWasPath: C{bool}
    """
    def __init__(self, module):
        state = _InternalState(self)
        state._module = module
        state._deprecatedAttributes = {}
        state._lastWasPath = False


    def __repr__(self):
        """
        Get a string containing the type of the module proxy and a
        representation of the wrapped module object.
        """
        state = _InternalState(self)
        return '<%s module=%r>' % (type(self).__name__, state._module)


    def __setattr__(self, name, value):
        """
        Set an attribute on the wrapped module object.
        """
        state = _InternalState(self)
        state._lastWasPath = False
        setattr(state._module, name, value)


    def __getattribute__(self, name):
        """
        Get an attribute from the module object, possibly emitting a warning.

        If the specified name has been deprecated, then a warning is issued.
        (Unless certain obscure conditions are met; see
        L{_ModuleProxy._lastWasPath} for more information about what might quash
        such a warning.)
        """
        state = _InternalState(self)
        if state._lastWasPath:
            deprecatedAttribute = None
        else:
            deprecatedAttribute = state._deprecatedAttributes.get(name)

        if deprecatedAttribute is not None:
            # If we have a _DeprecatedAttribute object from the earlier lookup,
            # allow it to issue the warning.
            value = deprecatedAttribute.get()
        else:
            # Otherwise, just retrieve the underlying value directly; it's not
            # deprecated, there's no warning to issue.
            value = getattr(state._module, name)
        if name == '__path__':
            state._lastWasPath = True
        else:
            state._lastWasPath = False
        return value



class _DeprecatedAttribute(object):
    """
    Wrapper for deprecated attributes.

    This is intended to be used by L{_ModuleProxy}. Calling
    L{_DeprecatedAttribute.get} will issue a warning and retrieve the
    underlying attribute's value.

    @type module: C{module}
    @ivar module: The original module instance containing this attribute

    @type fqpn: C{str}
    @ivar fqpn: Fully qualified Python name for the deprecated attribute

    @type version: L{twisted.python.versions.Version}
    @ivar version: Version that the attribute was deprecated in

    @type message: C{str}
    @ivar message: Deprecation message
    """
    def __init__(self, module, name, version, message):
        """
        Initialise a deprecated name wrapper.
        """
        self.module = module
        self.__name__ = name
        self.fqpn = module.__name__ + '.' + name
        self.version = version
        self.message = message


    def get(self):
        """
        Get the underlying attribute value and issue a deprecation warning.
        """
        # This might fail if the deprecated thing is a module inside a package.
        # In that case, don't emit the warning this time.  The import system
        # will come back again when it's not an AttributeError and we can emit
        # the warning then.
        result = getattr(self.module, self.__name__)
        message = _getDeprecationWarningString(self.fqpn, self.version,
            DEPRECATION_WARNING_FORMAT + ': ' + self.message)
        warn(message, DeprecationWarning, stacklevel=3)
        return result



def _deprecateAttribute(proxy, name, version, message):
    """
    Mark a module-level attribute as being deprecated.

    @type proxy: L{_ModuleProxy}
    @param proxy: The module proxy instance proxying the deprecated attributes

    @type name: C{str}
    @param name: Attribute name

    @type version: L{twisted.python.versions.Version}
    @param version: Version that the attribute was deprecated in

    @type message: C{str}
    @param message: Deprecation message
    """
    _module = object.__getattribute__(proxy, '_module')
    attr = _DeprecatedAttribute(_module, name, version, message)
    # Add a deprecated attribute marker for this module's attribute. When this
    # attribute is accessed via _ModuleProxy a warning is emitted.
    _deprecatedAttributes = object.__getattribute__(
        proxy, '_deprecatedAttributes')
    _deprecatedAttributes[name] = attr



def deprecatedModuleAttribute(version, message, moduleName, name):
    """
    Declare a module-level attribute as being deprecated.

    @type version: L{twisted.python.versions.Version}
    @param version: Version that the attribute was deprecated in

    @type message: C{str}
    @param message: Deprecation message

    @type moduleName: C{str}
    @param moduleName: Fully-qualified Python name of the module containing
        the deprecated attribute; if called from the same module as the
        attributes are being deprecated in, using the C{__name__} global can
        be helpful

    @type name: C{str}
    @param name: Attribute name to deprecate
    """
    module = sys.modules[moduleName]
    if not isinstance(module, _ModuleProxy):
        module = _ModuleProxy(module)
        sys.modules[moduleName] = module

    _deprecateAttribute(module, name, version, message)


def warnAboutFunction(offender, warningString):
    """
    Issue a warning string, identifying C{offender} as the responsible code.

    This function is used to deprecate some behavior of a function.  It differs
    from L{warnings.warn} in that it is not limited to deprecating the behavior
    of a function currently on the call stack.

    @param function: The function that is being deprecated.

    @param warningString: The string that should be emitted by this warning.
    @type warningString: C{str}

    @since: 11.0
    """
    # inspect.getmodule() is attractive, but somewhat
    # broken in Python < 2.6.  See Python bug 4845.
    offenderModule = sys.modules[offender.__module__]
    filename = inspect.getabsfile(offenderModule)
    lineStarts = list(findlinestarts(offender.__code__))
    lastLineNo = lineStarts[-1][1]
    globals = offender.__globals__

    kwargs = dict(
        category=DeprecationWarning,
        filename=filename,
        lineno=lastLineNo,
        module=offenderModule.__name__,
        registry=globals.setdefault("__warningregistry__", {}),
        module_globals=None)

    warn_explicit(warningString, **kwargs)



def _passed(argspec, positional, keyword):
    """
    Take an I{inspect.ArgSpec}, a tuple of positional arguments, and a dict of
    keyword arguments, and return a mapping of arguments that were actually
    passed to their passed values.

    @param argspec: The argument specification for the function to inspect.
    @type argspec: I{inspect.ArgSpec}

    @param positional: The positional arguments that were passed.
    @type positional: L{tuple}

    @param keyword: The keyword arguments that were passed.
    @type keyword: L{dict}

    @return: A dictionary mapping argument names (those declared in C{argspec})
        to values that were passed explicitly by the user.
    @rtype: L{dict} mapping L{str} to L{object}
    """
    result = {}
    unpassed = len(argspec.args) - len(positional)
    if argspec.keywords is not None:
        kwargs = result[argspec.keywords] = {}
    if unpassed < 0:
        if argspec.varargs is None:
            raise TypeError("Too many arguments.")
        else:
            result[argspec.varargs] = positional[len(argspec.args):]
    for name, value in zip(argspec.args, positional):
        result[name] = value
    for name, value in keyword.items():
        if name in argspec.args:
            if name in result:
                raise TypeError("Already passed.")
            result[name] = value
        elif argspec.keywords is not None:
            kwargs[name] = value
        else:
            raise TypeError("no such param")
    return result



def _mutuallyExclusiveArguments(argumentPairs):
    """
    Decorator which causes its decoratee to raise a L{TypeError} if two of the
    given arguments are passed at the same time.

    @param argumentPairs: pairs of argument identifiers, each pair indicating
        an argument that may not be passed in conjunction with another.
    @type argumentPairs: sequence of 2-sequences of L{str}

    @return: A decorator, used like so::

            @_mutuallyExclusiveArguments([["tweedledum", "tweedledee"]])
            def function(tweedledum=1, tweedledee=2):
                "Don't pass tweedledum and tweedledee at the same time."

    @rtype: 1-argument callable taking a callable and returning a callable.
    """
    def wrapper(wrappee):
        argspec = inspect.getargspec(wrappee)
        @wraps(wrappee)
        def wrapped(*args, **kwargs):
            arguments = _passed(argspec, args, kwargs)
            for this, that in argumentPairs:
                if this in arguments and that in arguments:
                    raise TypeError("nope")
            return wrappee(*args, **kwargs)
        return wrapped
    return wrapper
