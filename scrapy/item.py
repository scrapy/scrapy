"""
Scrapy Item

See documentation in docs/topics/item.rst
"""

from abc import ABCMeta
from collections.abc import MutableMapping
from copy import deepcopy
from pprint import pformat
from warnings import warn

from scrapy.utils.deprecate import ScrapyDeprecationWarning
from scrapy.utils.trackref import object_ref


class BaseItem(object_ref):
    """Base class for all scraped items.

    In Scrapy, an object is considered an *item* if it is an instance of either
    :class:`BaseItem` or :class:`dict`. For example, when the output of a
    spider callback is evaluated, only instances of :class:`BaseItem` or
    :class:`dict` are passed to :ref:`item pipelines <topics-item-pipeline>`.

    If you need instances of a custom class to be considered items by Scrapy,
    you must inherit from either :class:`BaseItem` or :class:`dict`.

    Unlike instances of :class:`dict`, instances of :class:`BaseItem` may be
    :ref:`tracked <topics-leaks-trackrefs>` to debug memory leaks.
    """
    pass


class Field(dict):
    """Container of field metadata"""


class ItemMeta(ABCMeta):
    """Metaclass_ of :class:`Item` that handles field definitions.

    .. _metaclass: https://realpython.com/python-metaclasses
    """

    def __new__(mcs, class_name, bases, attrs):
        classcell = attrs.pop('__classcell__', None)
        new_bases = tuple(base._class for base in bases if hasattr(base, '_class'))
        _class = super(ItemMeta, mcs).__new__(mcs, 'x_' + class_name, new_bases, attrs)

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
        return super(ItemMeta, mcs).__new__(mcs, class_name, bases, new_attrs)


class DictItem(MutableMapping, BaseItem):

    fields = {}

    def __new__(cls, *args, **kwargs):
        if issubclass(cls, DictItem) and not issubclass(cls, Item):
            warn('scrapy.item.DictItem is deprecated, please use '
                 'scrapy.item.Item instead',
                 ScrapyDeprecationWarning, stacklevel=2)
        return super(DictItem, cls).__new__(cls, *args, **kwargs)

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
            raise KeyError("%s does not support field: %s" %
                (self.__class__.__name__, key))

    def __delitem__(self, key):
        del self._values[key]

    def __getattr__(self, name):
        if name in self.fields:
            raise AttributeError("Use item[%r] to get field value" % name)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        if not name.startswith('_'):
            raise AttributeError("Use item[%r] = %r to set field value" %
                (name, value))
        super(DictItem, self).__setattr__(name, value)

    def __len__(self):
        return len(self._values)

    def __iter__(self):
        return iter(self._values)

    __hash__ = BaseItem.__hash__

    def keys(self):
        return self._values.keys()

    def __repr__(self):
        return pformat(dict(self))

    def copy(self):
        return self.__class__(self)

    def deepcopy(self):
        """Return a `deep copy`_ of this item.

        .. _deep copy: https://docs.python.org/library/copy.html#copy.deepcopy
        """
        return deepcopy(self)


class Item(DictItem, metaclass=ItemMeta):
    pass
