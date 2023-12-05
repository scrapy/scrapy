# -*- test-case-name: twisted.python.test.test_deprecate -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Deprecation framework for Twisted.

To mark a method, function, or class as being deprecated do this::

    from incremental import Version
    from twisted.python.deprecate import deprecated

    @deprecated(Version("Twisted", 22, 10, 0))
    def badAPI(self, first, second):
        '''
        Docstring for badAPI.
        '''
        ...

    @deprecated(Version("Twisted", 22, 10, 0))
    class BadClass:
        '''
        Docstring for BadClass.
        '''

The newly-decorated badAPI will issue a warning when called, and BadClass will
issue a warning when instantiated. Both will also have  a deprecation notice
appended to their docstring.

To deprecate properties you can use::

    from incremental import Version
    from twisted.python.deprecate import deprecatedProperty

    class OtherwiseUndeprecatedClass:

        @deprecatedProperty(Version("Twisted", 22, 10, 0))
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
        Version("Twisted", 22, 10, 0),
        "Use goodAttribute instead.",
        "your.full.module.name",
        "badAttribute")

The deprecated attributes will issue a warning whenever they are accessed. If
the attributes being deprecated are in the same module as the
L{deprecatedModuleAttribute} call is being made from, the C{__name__} global
can be used as the C{moduleName} parameter.


To mark an optional, keyword parameter of a function or method as deprecated
without deprecating the function itself, you can use::

    @deprecatedKeywordParameter(Version("Twisted", 22, 10, 0), "baz")
    def someFunction(foo, bar=0, baz=None):
        ...

See also L{incremental.Version}.

@type DEPRECATION_WARNING_FORMAT: C{str}
@var DEPRECATION_WARNING_FORMAT: The default deprecation warning string format
    to use when one is not provided by the user.
"""


__all__ = [
    "deprecated",
    "deprecatedProperty",
    "getDeprecationWarningString",
    "getWarningMethod",
    "setWarningMethod",
    "deprecatedModuleAttribute",
    "deprecatedKeywordParameter",
]


import inspect
import sys
from dis import findlinestarts
from functools import wraps
from types import ModuleType
from typing import Any, Callable, Dict, Optional, TypeVar, cast
from warnings import warn, warn_explicit

from incremental import Version, getVersionString

DEPRECATION_WARNING_FORMAT = "%(fqpn)s was deprecated in %(version)s"

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
        return f"{moduleName}.{name}"
    elif inspect.ismethod(obj):
        return f"{obj.__module__}.{obj.__qualname__}"
    return name


# Try to keep it looking like something in twisted.python.reflect.
_fullyQualifiedName.__module__ = "twisted.python.reflect"
_fullyQualifiedName.__name__ = "fullyQualifiedName"
_fullyQualifiedName.__qualname__ = "fullyQualifiedName"


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
    return f"please use {replacement} instead"


def _getDeprecationDocstring(version, replacement=None):
    """
    Generate an addition to a deprecated object's docstring that explains its
    deprecation.

    @param version: the version it was deprecated.
    @type version: L{incremental.Version}

    @param replacement: The replacement, if specified.
    @type replacement: C{str} or callable

    @return: a string like "Deprecated in Twisted 27.2.0; please use
        twisted.timestream.tachyon.flux instead."
    """
    doc = f"Deprecated in {getVersionString(version)}"
    if replacement:
        doc = f"{doc}; {_getReplacementString(replacement)}"
    return doc + "."


def _getDeprecationWarningString(fqpn, version, format=None, replacement=None):
    """
    Return a string indicating that the Python name was deprecated in the given
    version.

    @param fqpn: Fully qualified Python name of the thing being deprecated
    @type fqpn: C{str}

    @param version: Version that C{fqpn} was deprecated in.
    @type version: L{incremental.Version}

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
    warningString = format % {"fqpn": fqpn, "version": getVersionString(version)}
    if replacement:
        warningString = "{}; {}".format(
            warningString, _getReplacementString(replacement)
        )
    return warningString


def getDeprecationWarningString(callableThing, version, format=None, replacement=None):
    """
    Return a string indicating that the callable was deprecated in the given
    version.

    @type callableThing: C{callable}
    @param callableThing: Callable object to be deprecated

    @type version: L{incremental.Version}
    @param version: Version that C{callableThing} was deprecated in.

    @type format: C{str}
    @param format: A user-provided format to interpolate warning values into,
        or L{DEPRECATION_WARNING_FORMAT
        <twisted.python.deprecate.DEPRECATION_WARNING_FORMAT>} if L{None} is
        given

    @param replacement: what should be used in place of the callable. Either
        pass in a string, which will be inserted into the warning message,
        or a callable, which will be expanded to its full import path.
    @type replacement: C{str} or callable

    @return: A string describing the deprecation.
    @rtype: C{str}
    """
    return _getDeprecationWarningString(
        _fullyQualifiedName(callableThing), version, format, replacement
    )


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
        docstringLines.extend(["", textToAppend, ""])
    else:
        spaces = docstringLines.pop()
        docstringLines.extend(["", spaces + textToAppend, spaces])
    thingWithDoc.__doc__ = "\n".join(docstringLines)


def deprecated(version, replacement=None):
    """
    Return a decorator that marks callables as deprecated. To deprecate a
    property, see L{deprecatedProperty}.

    @type version: L{incremental.Version}
    @param version: The version in which the callable will be marked as
        having been deprecated.  The decorated function will be annotated
        with this version, having it set as its C{deprecatedVersion}
        attribute.

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
            function, version, None, replacement
        )

        @wraps(function)
        def deprecatedFunction(*args, **kwargs):
            warn(warningString, DeprecationWarning, stacklevel=2)
            return function(*args, **kwargs)

        _appendToDocstring(
            deprecatedFunction, _getDeprecationDocstring(version, replacement)
        )
        deprecatedFunction.deprecatedVersion = version  # type: ignore[attr-defined]
        return deprecatedFunction

    return deprecationDecorator


def deprecatedProperty(version, replacement=None):
    """
    Return a decorator that marks a property as deprecated. To deprecate a
    regular callable or class, see L{deprecated}.

    @type version: L{incremental.Version}
    @param version: The version in which the callable will be marked as
        having been deprecated.  The decorated function will be annotated
        with this version, having it set as its C{deprecatedVersion}
        attribute.

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
                    self.warningString,  # type: ignore[attr-defined]
                    DeprecationWarning,
                    stacklevel=2,
                )
                return function(*args, **kwargs)

            return deprecatedFunction

        def setter(self, function):
            return property.setter(self, self._deprecatedWrapper(function))

    def deprecationDecorator(function):
        warningString = getDeprecationWarningString(
            function, version, None, replacement
        )

        @wraps(function)
        def deprecatedFunction(*args, **kwargs):
            warn(warningString, DeprecationWarning, stacklevel=2)
            return function(*args, **kwargs)

        _appendToDocstring(
            deprecatedFunction, _getDeprecationDocstring(version, replacement)
        )
        deprecatedFunction.deprecatedVersion = version  # type: ignore[attr-defined]

        result = _DeprecatedProperty(deprecatedFunction)
        result.warningString = warningString  # type: ignore[attr-defined]
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


class _InternalState:
    """
    An L{_InternalState} is a helper object for a L{_ModuleProxy}, so that it
    can easily access its own attributes, bypassing its logic for delegating to
    another object that it's proxying for.

    @ivar proxy: a L{_ModuleProxy}
    """

    def __init__(self, proxy):
        object.__setattr__(self, "proxy", proxy)

    def __getattribute__(self, name):
        return object.__getattribute__(object.__getattribute__(self, "proxy"), name)

    def __setattr__(self, name, value):
        return object.__setattr__(object.__getattribute__(self, "proxy"), name, value)


class _ModuleProxy:
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

    def __repr__(self) -> str:
        """
        Get a string containing the type of the module proxy and a
        representation of the wrapped module object.
        """
        state = _InternalState(self)
        return f"<{type(self).__name__} module={state._module!r}>"

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
        if name == "__path__":
            state._lastWasPath = True
        else:
            state._lastWasPath = False
        return value


class _DeprecatedAttribute:
    """
    Wrapper for deprecated attributes.

    This is intended to be used by L{_ModuleProxy}. Calling
    L{_DeprecatedAttribute.get} will issue a warning and retrieve the
    underlying attribute's value.

    @type module: C{module}
    @ivar module: The original module instance containing this attribute

    @type fqpn: C{str}
    @ivar fqpn: Fully qualified Python name for the deprecated attribute

    @type version: L{incremental.Version}
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
        self.fqpn = module.__name__ + "." + name
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
        message = _getDeprecationWarningString(
            self.fqpn, self.version, DEPRECATION_WARNING_FORMAT + ": " + self.message
        )
        warn(message, DeprecationWarning, stacklevel=3)
        return result


def _deprecateAttribute(proxy, name, version, message):
    """
    Mark a module-level attribute as being deprecated.

    @type proxy: L{_ModuleProxy}
    @param proxy: The module proxy instance proxying the deprecated attributes

    @type name: C{str}
    @param name: Attribute name

    @type version: L{incremental.Version}
    @param version: Version that the attribute was deprecated in

    @type message: C{str}
    @param message: Deprecation message
    """
    _module = object.__getattribute__(proxy, "_module")
    attr = _DeprecatedAttribute(_module, name, version, message)
    # Add a deprecated attribute marker for this module's attribute. When this
    # attribute is accessed via _ModuleProxy a warning is emitted.
    _deprecatedAttributes = object.__getattribute__(proxy, "_deprecatedAttributes")
    _deprecatedAttributes[name] = attr


def deprecatedModuleAttribute(version, message, moduleName, name):
    """
    Declare a module-level attribute as being deprecated.

    @type version: L{incremental.Version}
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
        module = cast(ModuleType, _ModuleProxy(module))
        sys.modules[moduleName] = module

    _deprecateAttribute(module, name, version, message)


def warnAboutFunction(offender, warningString):
    """
    Issue a warning string, identifying C{offender} as the responsible code.

    This function is used to deprecate some behavior of a function.  It differs
    from L{warnings.warn} in that it is not limited to deprecating the behavior
    of a function currently on the call stack.

    @param offender: The function that is being deprecated.

    @param warningString: The string that should be emitted by this warning.
    @type warningString: C{str}

    @since: 11.0
    """
    # inspect.getmodule() is attractive, but somewhat
    # broken in Python < 2.6.  See Python bug 4845.
    offenderModule = sys.modules[offender.__module__]
    warn_explicit(
        warningString,
        category=DeprecationWarning,
        filename=inspect.getabsfile(offenderModule),
        lineno=max(lineNumber for _, lineNumber in findlinestarts(offender.__code__)),
        module=offenderModule.__name__,
        registry=offender.__globals__.setdefault("__warningregistry__", {}),
        module_globals=None,
    )


def _passedArgSpec(argspec, positional, keyword):
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
    result: Dict[str, object] = {}
    unpassed = len(argspec.args) - len(positional)
    if argspec.keywords is not None:
        kwargs = result[argspec.keywords] = {}
    if unpassed < 0:
        if argspec.varargs is None:
            raise TypeError("Too many arguments.")
        else:
            result[argspec.varargs] = positional[len(argspec.args) :]
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


def _passedSignature(signature, positional, keyword):
    """
    Take an L{inspect.Signature}, a tuple of positional arguments, and a dict of
    keyword arguments, and return a mapping of arguments that were actually
    passed to their passed values.

    @param signature: The signature of the function to inspect.
    @type signature: L{inspect.Signature}

    @param positional: The positional arguments that were passed.
    @type positional: L{tuple}

    @param keyword: The keyword arguments that were passed.
    @type keyword: L{dict}

    @return: A dictionary mapping argument names (those declared in
        C{signature}) to values that were passed explicitly by the user.
    @rtype: L{dict} mapping L{str} to L{object}
    """
    result = {}
    kwargs = None
    numPositional = 0
    for (n, (name, param)) in enumerate(signature.parameters.items()):
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            # Varargs, for example: *args
            result[name] = positional[n:]
            numPositional = len(result[name]) + 1
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            # Variable keyword args, for example: **my_kwargs
            kwargs = result[name] = {}
        elif param.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        ):
            if n < len(positional):
                result[name] = positional[n]
                numPositional += 1
        elif param.kind == inspect.Parameter.KEYWORD_ONLY:
            if name not in keyword:
                if param.default == inspect.Parameter.empty:
                    raise TypeError(f"missing keyword arg {name}")
                else:
                    result[name] = param.default
        else:
            raise TypeError(f"'{name}' parameter is invalid kind: {param.kind}")

    if len(positional) > numPositional:
        raise TypeError("Too many arguments.")
    for name, value in keyword.items():
        if name in signature.parameters.keys():
            if name in result:
                raise TypeError("Already passed.")
            result[name] = value
        elif kwargs is not None:
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
        spec = inspect.signature(wrappee)
        _passed = _passedSignature

        @wraps(wrappee)
        def wrapped(*args, **kwargs):
            arguments = _passed(spec, args, kwargs)
            for this, that in argumentPairs:
                if this in arguments and that in arguments:
                    raise TypeError(
                        ("The %r and %r arguments to %s " "are mutually exclusive.")
                        % (this, that, _fullyQualifiedName(wrappee))
                    )
            return wrappee(*args, **kwargs)

        return wrapped

    return wrapper


_Tc = TypeVar("_Tc", bound=Callable[..., Any])


def deprecatedKeywordParameter(
    version: Version, name: str, replacement: Optional[str] = None
) -> Callable[[_Tc], _Tc]:
    """
    Return a decorator that marks a keyword parameter of a callable
    as deprecated. A warning will be emitted if a caller supplies
    a value for the parameter, whether the caller uses a keyword or
    positional syntax.

    @type version: L{incremental.Version}
    @param version: The version in which the parameter will be marked as
        having been deprecated.

    @type name: L{str}
    @param name: The name of the deprecated parameter.

    @type replacement: L{str}
    @param replacement: Optional text indicating what should be used in
        place of the deprecated parameter.

    @since: Twisted 21.2.0
    """

    def wrapper(wrappee: _Tc) -> _Tc:
        warningString = _getDeprecationWarningString(
            f"The {name!r} parameter to {_fullyQualifiedName(wrappee)}",
            version,
            replacement=replacement,
        )

        doc = "The {!r} parameter was deprecated in {}".format(
            name,
            getVersionString(version),
        )
        if replacement:
            doc = doc + "; " + _getReplacementString(replacement)
        doc += "."

        params = inspect.signature(wrappee).parameters
        if (
            name in params
            and params[name].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
        ):
            parameterIndex = list(params).index(name)

            def checkDeprecatedParameter(*args, **kwargs):
                if len(args) > parameterIndex or name in kwargs:
                    warn(warningString, DeprecationWarning, stacklevel=2)
                return wrappee(*args, **kwargs)

        else:

            def checkDeprecatedParameter(*args, **kwargs):
                if name in kwargs:
                    warn(warningString, DeprecationWarning, stacklevel=2)
                return wrappee(*args, **kwargs)

        decorated = cast(_Tc, wraps(wrappee)(checkDeprecatedParameter))
        _appendToDocstring(decorated, doc)
        return decorated

    return wrapper
