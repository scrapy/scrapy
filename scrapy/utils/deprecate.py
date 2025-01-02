"""Some helpers for deprecation messages"""

from __future__ import annotations

import inspect
import warnings
from typing import Any, overload

from scrapy.exceptions import ScrapyDeprecationWarning


def attribute(obj: Any, oldattr: str, newattr: str, version: str = "0.12") -> None:
    cname = obj.__class__.__name__
    warnings.warn(
        f"{cname}.{oldattr} attribute is deprecated and will be no longer supported "
        f"in Scrapy {version}, use {cname}.{newattr} attribute instead",
        ScrapyDeprecationWarning,
        stacklevel=3,
    )


def create_deprecated_class(
    name: str,
    new_class: type,
    clsdict: dict[str, Any] | None = None,
    warn_category: type[Warning] = ScrapyDeprecationWarning,
    warn_once: bool = True,
    old_class_path: str | None = None,
    new_class_path: str | None = None,
    subclass_warn_message: str = "{cls} inherits from deprecated class {old}, please inherit from {new}.",
    instance_warn_message: str = "{cls} is deprecated, instantiate {new} instead.",
) -> type:
    """
    Return a "deprecated" class that causes its subclasses to issue a warning.
    Subclasses of ``new_class`` are considered subclasses of this class.
    It also warns when the deprecated class is instantiated, but do not when
    its subclasses are instantiated.

    It can be used to rename a base class in a library. For example, if we
    have

        class OldName(SomeClass):
            # ...

    and we want to rename it to NewName, we can do the following::

        class NewName(SomeClass):
            # ...

        OldName = create_deprecated_class('OldName', NewName)

    Then, if user class inherits from OldName, warning is issued. Also, if
    some code uses ``issubclass(sub, OldName)`` or ``isinstance(sub(), OldName)``
    checks they'll still return True if sub is a subclass of NewName instead of
    OldName.
    """

    # https://github.com/python/mypy/issues/4177
    class DeprecatedClass(new_class.__class__):  # type: ignore[misc, name-defined]
        # pylint: disable=no-self-argument
        deprecated_class: type | None = None
        warned_on_subclass: bool = False

        def __new__(  # pylint: disable=bad-classmethod-argument
            metacls, name: str, bases: tuple[type, ...], clsdict_: dict[str, Any]
        ) -> type:
            cls = super().__new__(metacls, name, bases, clsdict_)
            if metacls.deprecated_class is None:
                metacls.deprecated_class = cls
            return cls

        def __init__(cls, name: str, bases: tuple[type, ...], clsdict_: dict[str, Any]):
            meta = cls.__class__
            old = meta.deprecated_class
            if old in bases and not (warn_once and meta.warned_on_subclass):
                meta.warned_on_subclass = True
                msg = subclass_warn_message.format(
                    cls=_clspath(cls),
                    old=_clspath(old, old_class_path),
                    new=_clspath(new_class, new_class_path),
                )
                if warn_once:
                    msg += " (warning only on first subclass, there may be others)"
                warnings.warn(msg, warn_category, stacklevel=2)
            super().__init__(name, bases, clsdict_)

        # see https://www.python.org/dev/peps/pep-3119/#overloading-isinstance-and-issubclass
        # and https://docs.python.org/reference/datamodel.html#customizing-instance-and-subclass-checks
        # for implementation details
        def __instancecheck__(cls, inst: Any) -> bool:
            return any(cls.__subclasscheck__(c) for c in (type(inst), inst.__class__))

        def __subclasscheck__(cls, sub: type) -> bool:
            if cls is not DeprecatedClass.deprecated_class:
                # we should do the magic only if second `issubclass` argument
                # is the deprecated class itself - subclasses of the
                # deprecated class should not use custom `__subclasscheck__`
                # method.
                return super().__subclasscheck__(sub)

            if not inspect.isclass(sub):
                raise TypeError("issubclass() arg 1 must be a class")

            mro = getattr(sub, "__mro__", ())
            return any(c in {cls, new_class} for c in mro)

        def __call__(cls, *args: Any, **kwargs: Any) -> Any:
            old = DeprecatedClass.deprecated_class
            if cls is old:
                msg = instance_warn_message.format(
                    cls=_clspath(cls, old_class_path),
                    new=_clspath(new_class, new_class_path),
                )
                warnings.warn(msg, warn_category, stacklevel=2)
            return super().__call__(*args, **kwargs)

    deprecated_cls = DeprecatedClass(name, (new_class,), clsdict or {})

    try:
        frm = inspect.stack()[1]
        parent_module = inspect.getmodule(frm[0])
        if parent_module is not None:
            deprecated_cls.__module__ = parent_module.__name__
    except Exception as e:
        # Sometimes inspect.stack() fails (e.g. when the first import of
        # deprecated class is in jinja2 template). __module__ attribute is not
        # important enough to raise an exception as users may be unable
        # to fix inspect.stack() errors.
        warnings.warn(f"Error detecting parent module: {e!r}")

    return deprecated_cls


def _clspath(cls: type, forced: str | None = None) -> str:
    if forced is not None:
        return forced
    return f"{cls.__module__}.{cls.__name__}"


DEPRECATION_RULES: list[tuple[str, str]] = []


@overload
def update_classpath(path: str) -> str: ...


@overload
def update_classpath(path: Any) -> Any: ...


def update_classpath(path: Any) -> Any:
    """Update a deprecated path from an object with its new location"""
    for prefix, replacement in DEPRECATION_RULES:
        if isinstance(path, str) and path.startswith(prefix):
            new_path = path.replace(prefix, replacement, 1)
            warnings.warn(
                f"`{path}` class is deprecated, use `{new_path}` instead",
                ScrapyDeprecationWarning,
            )
            return new_path
    return path


def method_is_overridden(subclass: type, base_class: type, method_name: str) -> bool:
    """
    Return True if a method named ``method_name`` of a ``base_class``
    is overridden in a ``subclass``.

    >>> class Base:
    ...     def foo(self):
    ...         pass
    >>> class Sub1(Base):
    ...     pass
    >>> class Sub2(Base):
    ...     def foo(self):
    ...         pass
    >>> class Sub3(Sub1):
    ...     def foo(self):
    ...         pass
    >>> class Sub4(Sub2):
    ...     pass
    >>> method_is_overridden(Sub1, Base, 'foo')
    False
    >>> method_is_overridden(Sub2, Base, 'foo')
    True
    >>> method_is_overridden(Sub3, Base, 'foo')
    True
    >>> method_is_overridden(Sub4, Base, 'foo')
    True
    """
    base_method = getattr(base_class, method_name)
    sub_method = getattr(subclass, method_name)
    return base_method.__code__ is not sub_method.__code__
