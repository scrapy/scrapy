"""
Scrapy Item

See documentation in docs/topics/item.rst
"""

from abc import ABCMeta
from collections.abc import MutableMapping
from copy import deepcopy
from pprint import pformat
from typing import Dict

from scrapy.utils.trackref import object_ref


class Field(dict):
    """Container of field metadata"""


class ItemMeta(ABCMeta):
    """Metaclass_ of :class:`Item` that handles field definitions.

    .. _metaclass: https://realpython.com/python-metaclasses
    """

    def __new__(mcs, class_name, bases, attrs):
        classcell = attrs.pop('__classcell__', None)
        new_bases = tuple(base._class for base in bases if hasattr(base, '_class'))
        _class = super().__new__(mcs, 'x_' + class_name, new_bases, attrs)

        fields = getattr(_class, 'fields', {})
        new_attrs = {}
        for n in dir(_class):
            v = getattr(_class, n)
            if isinstance(v, Field):
                fields[n] = v
            elif n in attrs:
                new_attrs[n] = attrs[n]

        new_attrs['fields'] = fields
        new_attrs['_class'] = _class
        if classcell is not None:
            new_attrs['__classcell__'] = classcell
        return super().__new__(mcs, class_name, bases, new_attrs)


class Item(MutableMapping, object_ref, metaclass=ItemMeta):
    """
    Base class for scraped items.

    In Scrapy, an object is considered an ``item`` if it is an instance of either
    :class:`Item` or :class:`dict`, or any subclass. For example, when the output of a
    spider callback is evaluated, only instances of :class:`Item` or
    :class:`dict` are passed to :ref:`item pipelines <topics-item-pipeline>`.

    If you need instances of a custom class to be considered items by Scrapy,
    you must inherit from either :class:`Item` or :class:`dict`.

    Items must declare :class:`Field` attributes, which are processed and stored
    in the ``fields`` attribute. This restricts the set of allowed field names
    and prevents typos, raising ``KeyError`` when referring to undefined fields.
    Additionally, fields can be used to define metadata and control the way
    data is processed internally. Please refer to the :ref:`documentation
    about fields <topics-items-fields>` for additional information.

    Unlike instances of :class:`dict`, instances of :class:`Item` may be
    :ref:`tracked <topics-leaks-trackrefs>` to debug memory leaks.
    """

    fields: Dict[str, Field]

    def __init__(self, *args, **kwargs):
        self._values = {}
        if args or kwargs:  # avoid creating dict for most common case
            for k, v in dict(*args, **kwargs).items():
                self[k] = v

    def __getitem__(self, key):
        return self._values[key]

    def __setitem__(self, key, value):
        if key in self.fields:
            self._values[key] = value
        else:
            raise KeyError(f"{self.__class__.__name__} does not support field: {key}")

    def __delitem__(self, key):
        del self._values[key]

    def __getattr__(self, name):
        if name in self.fields:
            raise AttributeError(f"Use item[{name!r}] to get field value")
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if not name.startswith('_'):
            raise AttributeError(f"Use item[{name!r}] = {value!r} to set field value")
        super().__setattr__(name, value)

    def __len__(self):
        return len(self._values)

    def __iter__(self):
        return iter(self._values)

    __hash__ = object_ref.__hash__

    def keys(self):
        return self._values.keys()

    def __repr__(self):
        return pformat(dict(self))

    def copy(self):
        return self.__class__(self)

    def deepcopy(self):
        """Return a :func:`~copy.deepcopy` of this item.
        """
        return deepcopy(self)
