# The MIT License
#
# Copyright (c) 2009-2011 the bpython authors.
# Copyright (c) 2015 Sebastian Ramacher
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import inspect
import keyword
import pydoc
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional, Type, Dict, List, ContextManager
from types import MemberDescriptorType, TracebackType
from ._typing_compat import Literal

from pygments.token import Token
from pygments.lexers import Python3Lexer

from .lazyre import LazyReCompile


class _Repr:
    """
    Helper for `ArgSpec`: Returns the given value in `__repr__()`.
    """

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value

    def __repr__(self) -> str:
        return self.value

    __str__ = __repr__


@dataclass
class ArgSpec:
    args: List[str]
    varargs: Optional[str]
    varkwargs: Optional[str]
    defaults: Optional[List[_Repr]]
    kwonly: List[str]
    kwonly_defaults: Optional[Dict[str, _Repr]]
    annotations: Optional[Dict[str, Any]]


@dataclass
class FuncProps:
    func: str
    argspec: ArgSpec
    is_bound_method: bool


class AttrCleaner(ContextManager[None]):
    """A context manager that tries to make an object not exhibit side-effects
    on attribute lookup.

    Unless explicitly required, prefer `getattr_safe`."""

    def __init__(self, obj: Any) -> None:
        self._obj = obj

    def __enter__(self) -> None:
        """Try to make an object not exhibit side-effects on attribute
        lookup."""
        type_ = type(self._obj)
        # Dark magic:
        # If __getattribute__ doesn't exist on the class and __getattr__ does
        # then __getattr__ will be called when doing
        #   getattr(type_, '__getattribute__', None)
        # so we need to first remove the __getattr__, then the
        # __getattribute__, then look up the attributes and then restore the
        # original methods. :-(
        # The upshot being that introspecting on an object to display its
        # attributes will avoid unwanted side-effects.
        __getattr__ = getattr(type_, "__getattr__", None)
        if __getattr__ is not None:
            try:
                setattr(type_, "__getattr__", (lambda *_, **__: None))
            except TypeError:
                __getattr__ = None
        __getattribute__ = getattr(type_, "__getattribute__", None)
        if __getattribute__ is not None:
            try:
                setattr(type_, "__getattribute__", object.__getattribute__)
            except TypeError:
                # XXX: This happens for e.g. built-in types
                __getattribute__ = None
        self._attribs = (__getattribute__, __getattr__)
        # /Dark magic

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> Literal[False]:
        """Restore an object's magic methods."""
        type_ = type(self._obj)
        __getattribute__, __getattr__ = self._attribs
        # Dark magic:
        if __getattribute__ is not None:
            setattr(type_, "__getattribute__", __getattribute__)
        if __getattr__ is not None:
            setattr(type_, "__getattr__", __getattr__)
        # /Dark magic
        return False


def parsekeywordpairs(signature: str) -> Dict[str, str]:
    preamble = True
    stack = []
    substack: List[str] = []
    parendepth = 0
    annotation = False
    for token, value in Python3Lexer().get_tokens(signature):
        if preamble:
            if token is Token.Punctuation and value == "(":
                # First "(" starts the list of arguments
                preamble = False
            continue

        if token is Token.Punctuation:
            if value in "({[":
                parendepth += 1
            elif value in ")}]":
                parendepth -= 1
            elif value == ":":
                if parendepth == -1:
                    # End of signature reached
                    break
                elif parendepth == 0:
                    # Start of type annotation
                    annotation = True

            if (value, parendepth) in ((",", 0), (")", -1)):
                # End of current argument
                stack.append(substack)
                substack = []
                # If type annotation didn't end before, it does now.
                annotation = False
                continue
        elif token is Token.Operator and value == "=" and parendepth == 0:
            # End of type annotation
            annotation = False

        if value and not annotation and (parendepth > 0 or value.strip()):
            substack.append(value)

    return {item[0]: "".join(item[2:]) for item in stack if len(item) >= 3}


def _fix_default_values(f: Callable, argspec: ArgSpec) -> ArgSpec:
    """Functions taking default arguments that are references to other objects
    will cause breakage, so we swap out the object itself with the name it was
    referenced with in the source by parsing the source itself!"""

    if argspec.defaults is None and argspec.kwonly_defaults is None:
        # No keyword args, no need to do anything
        return argspec

    try:
        src, _ = inspect.getsourcelines(f)
    except (OSError, IndexError):
        # IndexError is raised in inspect.findsource(), can happen in
        # some situations. See issue #94.
        return argspec
    except TypeError:
        # No source code is available, so replace the default values with what we have.
        if argspec.defaults is not None:
            argspec.defaults = [_Repr(str(value)) for value in argspec.defaults]
        if argspec.kwonly_defaults is not None:
            argspec.kwonly_defaults = {
                key: _Repr(str(value))
                for key, value in argspec.kwonly_defaults.items()
            }
        return argspec

    kwparsed = parsekeywordpairs("".join(src))

    if argspec.defaults is not None:
        values = list(argspec.defaults)
        keys = argspec.args[-len(values) :]
        for i, key in enumerate(keys):
            values[i] = _Repr(kwparsed[key])

        argspec.defaults = values
    if argspec.kwonly_defaults is not None:
        for key in argspec.kwonly_defaults.keys():
            argspec.kwonly_defaults[key] = _Repr(kwparsed[key])

    return argspec


_getpydocspec_re = LazyReCompile(
    r"([a-zA-Z_][a-zA-Z0-9_]*?)\((.*?)\)", re.DOTALL
)


def _getpydocspec(f: Callable) -> Optional[ArgSpec]:
    try:
        argspec = pydoc.getdoc(f)
    except NameError:
        return None

    s = _getpydocspec_re.search(argspec)
    if s is None:
        return None

    if not hasattr_safe(f, "__name__") or s.groups()[0] != f.__name__:
        return None

    args = []
    defaults = []
    varargs = varkwargs = None
    kwonly_args = []
    kwonly_defaults = {}
    for arg in s.group(2).split(","):
        arg = arg.strip()
        if arg.startswith("**"):
            varkwargs = arg[2:]
        elif arg.startswith("*"):
            varargs = arg[1:]
        elif arg == "...":
            # At least print denotes "..." as separator between varargs and kwonly args.
            varargs = ""
        else:
            arg, _, default = arg.partition("=")
            if varargs is not None:
                kwonly_args.append(arg)
                if default:
                    kwonly_defaults[arg] = _Repr(default)
            else:
                args.append(arg)
                if default:
                    defaults.append(_Repr(default))

    return ArgSpec(
        args, varargs, varkwargs, defaults, kwonly_args, kwonly_defaults, None
    )


def getfuncprops(func: str, f: Callable) -> Optional[FuncProps]:
    # Check if it's a real bound method or if it's implicitly calling __init__
    # (i.e. FooClass(...) and not FooClass.__init__(...) -- the former would
    # not take 'self', the latter would:
    try:
        func_name = getattr(f, "__name__", None)
    except:
        # if calling foo.__name__ would result in an error
        func_name = None

    try:
        is_bound_method = (
            (inspect.ismethod(f) and f.__self__ is not None)
            or (func_name == "__init__" and not func.endswith(".__init__"))
            or (func_name == "__new__" and not func.endswith(".__new__"))
        )
    except:
        # if f is a method from a xmlrpclib.Server instance, func_name ==
        # '__init__' throws xmlrpclib.Fault (see #202)
        return None
    try:
        argspec = _get_argspec_from_signature(f)
        fprops = FuncProps(
            func, _fix_default_values(f, argspec), is_bound_method
        )
    except (TypeError, KeyError, ValueError):
        argspec_pydoc = _getpydocspec(f)
        if argspec_pydoc is None:
            return None
        if inspect.ismethoddescriptor(f):
            argspec_pydoc.args.insert(0, "obj")
        fprops = FuncProps(func, argspec_pydoc, is_bound_method)
    return fprops


def is_eval_safe_name(string: str) -> bool:
    return all(
        part.isidentifier() and not keyword.iskeyword(part)
        for part in string.split(".")
    )


def _get_argspec_from_signature(f: Callable) -> ArgSpec:
    """Get callable signature from inspect.signature in argspec format.

    inspect.signature is a Python 3 only function that returns the signature of
    a function.  Its advantage over inspect.getfullargspec is that it returns
    the signature of a decorated function, if the wrapper function itself is
    decorated with functools.wraps.

    """
    args = []
    varargs = None
    varkwargs = None
    defaults = []
    kwonly = []
    kwonly_defaults = {}
    annotations = {}

    # We use signature here instead of getfullargspec as the latter also returns
    # self and cls (for class methods).
    signature = inspect.signature(f)
    for parameter in signature.parameters.values():
        if parameter.annotation is not parameter.empty:
            annotations[parameter.name] = parameter.annotation

        if parameter.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD:
            args.append(parameter.name)
            if parameter.default is not parameter.empty:
                defaults.append(parameter.default)
        elif parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            args.append(parameter.name)
        elif parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            varargs = parameter.name
        elif parameter.kind == inspect.Parameter.KEYWORD_ONLY:
            kwonly.append(parameter.name)
            kwonly_defaults[parameter.name] = parameter.default
        elif parameter.kind == inspect.Parameter.VAR_KEYWORD:
            varkwargs = parameter.name

    return ArgSpec(
        args,
        varargs,
        varkwargs,
        defaults if defaults else None,
        kwonly,
        kwonly_defaults if kwonly_defaults else None,
        annotations if annotations else None,
    )


_get_encoding_line_re = LazyReCompile(r"^.*coding[:=]\s*([-\w.]+).*$")


def get_encoding(obj) -> str:
    """Try to obtain encoding information of the source of an object."""
    for line in inspect.findsource(obj)[0][:2]:
        m = _get_encoding_line_re.search(line)
        if m:
            return m.group(1)
    return "utf8"


def get_encoding_file(fname: str) -> str:
    """Try to obtain encoding information from a Python source file."""
    with open(fname, encoding="ascii", errors="ignore") as f:
        for _ in range(2):
            line = f.readline()
            match = _get_encoding_line_re.search(line)
            if match:
                return match.group(1)
    return "utf8"


def getattr_safe(obj: Any, name: str) -> Any:
    """Side effect free getattr (calls getattr_static)."""
    result = inspect.getattr_static(obj, name)
    # Slots are a MemberDescriptorType
    if isinstance(result, MemberDescriptorType):
        result = getattr(obj, name)
    # classmethods are safe to access (see #966)
    if isinstance(result, (classmethod, staticmethod)):
        result = result.__get__(obj, obj)
    return result


def hasattr_safe(obj: Any, name: str) -> bool:
    try:
        getattr_safe(obj, name)
        return True
    except AttributeError:
        return False
