"""
Scrapy Item

See documentation in docs/topics/items.rst
"""

from __future__ import annotations

from abc import ABCMeta
from collections.abc import MutableMapping
from copy import deepcopy
from pprint import pformat
from typing import TYPE_CHECKING, Any, NoReturn

from scrapy.utils.trackref import object_ref

if TYPE_CHECKING:
    from collections.abc import Iterator, KeysView

    # typing.Self requires Python 3.11
    from typing_extensions import Self


class Field(dict[str, Any]):
    """Container of field metadata"""


def _ordered_field_names(cls: type) -> list[str]:
    """Return the names of the :class:`Field` attributes of *cls* in definition
    order.

    Fields declared in base classes come first, ordered from the topmost base
    to the most derived class. Within each class, fields keep their definition
    order. A field redefined in a subclass keeps the position of its first
    definition.
    """
    names: list[str] = []
    seen: set[str] = set()
    for base in reversed(cls.__mro__):
        for name, value in vars(base).items():
            if isinstance(value, Field) and name not in seen:
                seen.add(name)
                names.append(name)
    return names


class ItemMeta(ABCMeta):
    """Metaclass_ of :class:`Item` that handles field definitions.

    .. _metaclass: https://realpython.com/python-metaclasses
    """

    def __new__(
        mcs, class_name: str, bases: tuple[type, ...], attrs: dict[str, Any]
    ) -> ItemMeta:
        classcell = attrs.pop("__classcell__", None)
        new_bases = tuple(base._class for base in bases if hasattr(base, "_class"))
        _class = super().__new__(mcs, "x_" + class_name, new_bases, attrs)

        fields = getattr(_class, "fields", {})
        for n in _ordered_field_names(_class):
            fields[n] = getattr(_class, n)
        new_attrs = {n: v for n, v in attrs.items() if not isinstance(v, Field)}

        new_attrs["fields"] = fields
        new_attrs["_class"] = _class
        if classcell is not None:
            new_attrs["__classcell__"] = classcell
        return super().__new__(mcs, class_name, bases, new_attrs)


class Item(MutableMapping[str, Any], object_ref, metaclass=ItemMeta):
    """Base class for scraped items.

    In Scrapy, an object is considered an ``item`` if it's supported by the
    `itemadapter`_ library. For example, when the output of a spider callback
    is evaluated, only such objects are passed to :ref:`item pipelines
    <topics-item-pipeline>`. :class:`Item` is one of the classes supported by
    `itemadapter`_ by default.

    Items must declare :class:`Field` attributes, which are processed and stored
    in the ``fields`` attribute. This restricts the set of allowed field names
    and prevents typos, raising ``KeyError`` when referring to undefined fields.
    Additionally, fields can be used to define metadata and control the way
    data is processed internally. Please refer to the :ref:`documentation
    about fields <topics-items-fields>` for additional information.

    Unlike instances of :class:`dict`, instances of :class:`Item` may be
    :ref:`tracked <topics-leaks-trackrefs>` to debug memory leaks.

    .. _itemadapter: https://github.com/scrapy/itemadapter
    """

    #: A dictionary containing *all declared fields* for this Item, not only
    #: those populated. The keys are the field names and the values are the
    #: :class:`Field` objects used in the :ref:`Item declaration
    #: <topics-items-declaring>`.
    #:
    #: Fields are kept in definition order: fields declared in base classes
    #: come first, followed by fields declared in subclasses, and a field
    #: redefined in a subclass keeps the position of its first definition.
    #:
    #: .. versionchanged:: VERSION
    #:    Fields are now returned in definition order rather than alphabetical
    #:    order.
    fields: dict[str, Field]

    def __init__(self, *args: Any, **kwargs: Any):
        self._values: dict[str, Any] = {}
        if args or kwargs:  # avoid creating dict for most common case
            for k, v in dict(*args, **kwargs).items():
                self[k] = v

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self.fields:
            self._values[key] = value
        else:
            raise KeyError(f"{self.__class__.__name__} does not support field: {key}")

    def __delitem__(self, key: str) -> None:
        del self._values[key]

    def __getattr__(self, name: str) -> NoReturn:
        if name in self.fields:
            raise AttributeError(f"Use item[{name!r}] to get field value")
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if not name.startswith("_"):
            raise AttributeError(f"Use item[{name!r}] = {value!r} to set field value")
        super().__setattr__(name, value)

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    __hash__ = object_ref.__hash__

    def keys(self) -> KeysView[str]:
        return self._values.keys()

    def __repr__(self) -> str:
        return pformat(dict(self))

    def copy(self) -> Self:
        return self.__class__(self)

    def deepcopy(self) -> Self:
        """Return a :func:`~copy.deepcopy` of this item."""
        return deepcopy(self)
