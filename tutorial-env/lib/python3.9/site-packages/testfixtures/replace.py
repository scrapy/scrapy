import os
from contextlib import contextmanager
from functools import partial
from gc import get_referrers, get_referents
from operator import setitem, getitem
from types import ModuleType
from typing import Any, TypeVar, Callable, Dict, Tuple

from testfixtures.resolve import resolve, not_there, Resolved, classmethod_type, class_type
from testfixtures.utils import wrap, extend_docstring

import warnings

# Should be Literal[setattr, getattr] but Python 3.8 only.
Accessor = Callable[[Any, str], Any]


def not_same_descriptor(x, y, descriptor):
    return isinstance(x, descriptor) and not isinstance(y, descriptor)


R = TypeVar('R')


class Replacer:
    """
    These are used to manage the mocking out of objects so that units
    of code can be tested without having to rely on their normal
    dependencies.
    """

    def __init__(self):
        self.originals: Dict[int, Tuple[Any, Resolved]] = {}

    def _replace(self, resolved: Resolved, value):
        if value is not_there:
            if resolved.setter is setattr:
                try:
                    delattr(resolved.container, resolved.name)
                except AttributeError:
                    pass
            if resolved.setter is setitem:
                try:
                    del resolved.container[resolved.name]
                except KeyError:
                    pass
        else:
            resolved.setter(resolved.container, resolved.name, value)

    def __call__(self, target: Any, replacement: R, strict: bool = True,
                 container: Any = None, accessor: Accessor = None, name: str = None) -> R:
        """
        Replace the specified target with the supplied replacement.
        """
        if name is None and accessor is not None:
            raise TypeError('accessor is not used unless name is specified')

        if isinstance(target, str):
            if name is not None:
                raise TypeError('name cannot be specified when target is a string')
            resolved = resolve(target, container)
        else:
            found = not_there
            if container is None:
                container = target

            name = name or getattr(target, '__name__', None)
            if name is None:
                raise TypeError('name must be specified when target is not a string')
            else:
                if accessor is None:
                    try:
                        accessor = getitem
                        found = accessor(container, name)
                    except KeyError:
                        pass
                    except TypeError:
                        accessor = getattr
                        found = accessor(container, name, not_there)
                else:
                    try:
                        found = accessor(container, name)
                    except (KeyError, AttributeError):
                        pass

            if strict and not (found is not_there or target is container):
                expected = accessor(container, name)
                if target is not expected:
                    raise AssertionError(f'{name!r} resolved to {found}, expected {target}')

            resolved = Resolved(
                container,
                setitem if accessor is getitem else setattr,
                name,
                found
            )

        if resolved.setter is None:
            raise ValueError('target must contain at least one dot!')
        if resolved.found is not_there and strict:
            raise AttributeError('Original %r not found' % resolved.name)

        replacement_to_use = replacement

        if isinstance(resolved.container, type):

            # if we have a descriptor, don't accidentally use the result of its __get__ method:
            if resolved.name in resolved.container.__dict__:
                resolved.found = resolved.container.__dict__[resolved.name]

            if not_same_descriptor(resolved.found, replacement, classmethod):
                replacement_to_use = classmethod(replacement)

            elif not_same_descriptor(resolved.found, replacement, staticmethod):
                replacement_to_use = staticmethod(replacement)

        self._replace(resolved, replacement_to_use)
        key = id(target)
        if key not in self.originals:
            self.originals[key] = target, resolved
        return replacement

    def replace(self, target: Any, replacement: Any, strict: bool = True,
                container: Any = None, accessor: Accessor = None, name: str = None) -> None:
        """
        Replace the specified target with the supplied replacement.
        """
        self(target, replacement, strict, container, accessor, name)

    def in_environ(self, name: str, replacement: Any) -> None:
        """
        This method provides a convenient way of ensuring an environment variable
        in :any:`os.environ` is set to a particular value.

        If you wish to ensure that an environment variable is *not* present,
        then use :any:`not_there` as the ``replacement``.
        """
        self(os.environ, name=name, accessor=getitem, strict=False,
             replacement=not_there if replacement is not_there else str(replacement))

    def _find_container(self, attribute, name: str, break_on_static: bool):
        for referrer in get_referrers(attribute):
            if break_on_static and isinstance(referrer, staticmethod):
                return None, referrer
            elif isinstance(referrer, dict) and '__dict__' in referrer:
                if referrer.get(name) is attribute:
                    for container in get_referrers(referrer):
                        if isinstance(container, type):
                            return container, None
        return None, None

    def on_class(self, attribute: Callable, replacement: Any, name: str = None) -> None:
        """
        This method provides a convenient way to replace methods, static methods and class
        methods on their classes.

        If the attribute being replaced has a ``__name__`` that differs from the attribute
        name on the class, such as that returned by poorly implemented decorators, then
        ``name`` must be used to provide the correct name.
        """
        if not callable(attribute):
            raise TypeError('attribute must be callable')
        name = name or getattr(attribute, '__name__', None)
        container = None
        if isinstance(attribute, classmethod_type):
            for referred in get_referents(attribute):
                if isinstance(referred, class_type):
                    container = referred
        else:
            container, staticmethod_ = self._find_container(attribute, name, break_on_static=True)
            if staticmethod_ is not None:
                container, _ = self._find_container(staticmethod_, name, break_on_static=False)

        if container is None:
            raise AttributeError(f'could not find container of {attribute!r} using name {name!r}')

        self(container, name=name, accessor=getattr, replacement=replacement)

    def in_module(self, target: Any, replacement: Any, module: ModuleType = None) -> None:
        """
        This method provides a convenient way to replace targets that are module globals,
        particularly functions or other objects with a ``__name__`` attribute.

        If an object has been imported into a module other than the one where it has been
        defined, then ``module`` should be used to specify the module where you would
        like the replacement to occur.
        """
        container = module or resolve(target.__module__).found
        name = target.__name__
        self(container, name=name, accessor=getattr, replacement=replacement)

    def restore(self) -> None:
        """
        Restore all the original objects that have been replaced by
        calls to the :meth:`replace` method of this :class:`Replacer`.
        """
        for id_, (target, original) in tuple(self.originals.items()):
            self._replace(original, original.found)
            del self.originals[id_]

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.restore()

    def __del__(self):
        if self.originals:
            # no idea why coverage misses the following statement
            # it's covered by test_replace.TestReplace.test_replacer_del
            warnings.warn(  # pragma: no cover
                'Replacer deleted without being restored, '
                'originals left: %r' % {k:v for (k, v) in self.originals.values()}
                )


def replace(
        target: Any, replacement: Any, strict: bool = True,
        container: Any = None, accessor: Accessor = None, name: str = None
) -> Callable[[Callable], Callable]:
    """
    A decorator to replace a target object for the duration of a test
    function.
    """
    r = Replacer()
    return wrap(
        partial(r.__call__, target, replacement, strict, container, accessor, name),
        r.restore
    )


@contextmanager
def replace_in_environ(name: str, replacement: Any):
    """
    This context manager provides a quick way to use :meth:`Replacer.in_environ`.
    """
    with Replacer() as r:
        r.in_environ(name, replacement)
        yield


@contextmanager
def replace_on_class(attribute: Callable, replacement: Any, name: str = None):
    """
    This context manager provides a quick way to use :meth:`Replacer.on_class`.
    """
    with Replacer() as r:
        r.on_class(attribute, replacement, name)
        yield


@contextmanager
def replace_in_module(target: Any, replacement: Any, module: ModuleType = None):
    """
    This context manager provides a quick way to use :meth:`Replacer.in_module`.
    """
    with Replacer() as r:
        r.in_module(target, replacement, module)
        yield


class Replace(object):
    """
    A context manager that uses a :class:`Replacer` to replace a single target.
    """

    def __init__(
            self, target: Any, replacement: R, strict: bool = True,
            container: Any = None, accessor: Accessor = None, name: str = None
    ):
        self.target = target
        self.replacement = replacement
        self.strict = strict
        self.container: Any = container
        self.accessor: Accessor = accessor
        self.name: str = name
        self._replacer = Replacer()

    def __enter__(self) -> R:
        return self._replacer(
            self.target, self.replacement, self.strict, self.container, self.accessor, self.name
        )

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._replacer.restore()


replace_params_doc = """
:param target: 

  This must be one of the following:
  
  - A string containing the dotted-path to the object to be replaced, in which case it will be 
    resolved the the object to be replaced.
    
    This path may specify a module in a package, an attribute of a module, or any attribute of 
    something contained within a module.
    
  - The container of the object to be replaced, in which case ``name`` must be specified.
  
  - The object to be replaced, in which case ``container`` must be specified.
    ``name`` must also be specified if it cannot be obtained from the ``__name__`` attribute
    of the object to be replaced.

:param replacement: The object to use as a replacement.

:param strict: When `True`, an exception will be raised if an
               attempt is made to replace an object that does
               not exist or if the object that is obtained using the ``accessor`` to 
               access the ``name`` from the ``container`` is not identical to the ``target``.
               
:param container: 
  The container of the object from which ``target`` can be accessed using either
  :func:`getattr` or :func:`~operator.getitem`.
  
:param accessor:
  Either :func:`getattr` or :func:`~operator.getitem`. If not supplied, this will be inferred
  preferring :func:`~operator.getitem` over :func:`getattr`.
  
:param name:
  The name used to access the ``target`` from the ``container`` using the ``accessor``.
  If required but not specified, the ``__name__`` attribute of the ``target`` will be used. 
"""

# add the param docs, so we only have one copy of them!
extend_docstring(replace_params_doc,
                 [Replacer.__call__, Replacer.replace, replace, Replace])
