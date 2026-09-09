"""Some helpers for deprecation messages"""

from __future__ import annotations

import inspect
import sys
import warnings
from typing import TYPE_CHECKING, Any, overload

from formerly import deprecated_class

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.python import get_func_args_dict

if sys.version_info >= (3, 13):
    from warnings import deprecated as _deprecated
else:
    from typing_extensions import deprecated as _deprecated

if TYPE_CHECKING:
    from collections.abc import Callable


_WRAPPER_MODULES = frozenset({__name__, _deprecated.__module__})


def attribute(obj: Any, oldattr: str, newattr: str, version: str = "0.12") -> None:
    cname = obj.__class__.__name__
    warnings.warn(
        f"{cname}.{oldattr} attribute is deprecated and will be no longer supported "
        f"in Scrapy {version}, use {cname}.{newattr} attribute instead",
        ScrapyDeprecationWarning,
        stacklevel=3,
    )


@_deprecated(
    "scrapy.utils.deprecate.create_deprecated_class() is deprecated, use"
    " formerly.deprecated_class() instead.",
    category=ScrapyDeprecationWarning,
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
    """Return a deprecated alias of *new_class* named *name*."""
    cls: type = deprecated_class(
        name,
        new_class,
        namespace=clsdict,
        category=warn_category,
        warn_once=warn_once,
        old_path=old_class_path,
        new_path=new_class_path,
        subclass_message=subclass_warn_message,
        instance_message=instance_warn_message,
    )
    # deprecated_class() takes the module of the alias from its calling frame,
    # which is this function and the decorator wrapping it, so skip past both.
    frame = inspect.currentframe()
    assert frame is not None
    while frame.f_globals.get("__name__") in _WRAPPER_MODULES:
        assert frame.f_back is not None
        frame = frame.f_back
    cls.__module__ = frame.f_globals.get("__name__", cls.__module__)
    return cls


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
                stacklevel=2,
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
    >>> method_is_overridden(Base, Base, 'foo')
    False
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


def argument_is_required(func: Callable[..., Any], arg_name: str) -> bool:
    """
    Check if a function argument is required (exists and doesn't have a default value).

    .. versionadded:: 2.14

    >>> def func(a, b=1, c=None):
    ...     pass
    >>> argument_is_required(func, 'a')
    True
    >>> argument_is_required(func, 'b')
    False
    >>> argument_is_required(func, 'c')
    False
    >>> argument_is_required(func, 'd')
    False
    """
    args = get_func_args_dict(func)
    param = args.get(arg_name)
    return param is not None and param.default is inspect.Parameter.empty


def warn_on_deprecated_spider_attribute(attribute_name: str, setting_name: str) -> None:
    warnings.warn(
        f"The '{attribute_name}' spider attribute is deprecated. "
        "Use Spider.custom_settings or Spider.update_settings() instead. "
        f"The corresponding setting name is '{setting_name}'.",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )
