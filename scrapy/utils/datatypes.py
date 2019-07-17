"""
This module contains data types used by Scrapy which are not included in the
Python Standard Library.

This module must not depend on any module outside the Standard Library.
"""

import copy
import collections
import warnings

import six

from scrapy.exceptions import ScrapyDeprecationWarning


if six.PY2:
    Mapping = collections.Mapping
else:
    Mapping = collections.abc.Mapping


class MultiValueDictKeyError(KeyError):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "scrapy.utils.datatypes.MultiValueDictKeyError is deprecated "
            "and will be removed in future releases.",
            category=ScrapyDeprecationWarning,
            stacklevel=2
        )
        super(MultiValueDictKeyError, self).__init__(*args, **kwargs)


class MultiValueDict(dict):
    """
    A subclass of dictionary customized to handle multiple values for the same key.

    >>> d = MultiValueDict({'name': ['Adrian', 'Simon'], 'position': ['Developer']})
    >>> d['name']
    'Simon'
    >>> d.getlist('name')
    ['Adrian', 'Simon']
    >>> d.get('lastname', 'nonexistent')
    'nonexistent'
    >>> d.setlist('lastname', ['Holovaty', 'Willison'])

    This class exists to solve the irritating problem raised by cgi.parse_qs,
    which returns a list for every key, even though most Web forms submit
    single name-value pairs.
    """
    def __init__(self, key_to_list_mapping=()):
        warnings.warn("scrapy.utils.datatypes.MultiValueDict is deprecated "
                      "and will be removed in future releases.",
                      category=ScrapyDeprecationWarning,
                      stacklevel=2)
        dict.__init__(self, key_to_list_mapping)

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, dict.__repr__(self))

    def __getitem__(self, key):
        """
        Returns the last data value for this key, or [] if it's an empty list;
        raises KeyError if not found.
        """
        try:
            list_ = dict.__getitem__(self, key)
        except KeyError:
            raise MultiValueDictKeyError("Key %r not found in %r" % (key, self))
        try:
            return list_[-1]
        except IndexError:
            return []

    def __setitem__(self, key, value):
        dict.__setitem__(self, key, [value])

    def __copy__(self):
        return self.__class__(dict.items(self))

    def __deepcopy__(self, memo=None):
        if memo is None:
            memo = {}
        result = self.__class__()
        memo[id(self)] = result
        for key, value in dict.items(self):
            dict.__setitem__(result, copy.deepcopy(key, memo), copy.deepcopy(value, memo))
        return result

    def get(self, key, default=None):
        "Returns the default value if the requested data doesn't exist"
        try:
            val = self[key]
        except KeyError:
            return default
        if val == []:
            return default
        return val

    def getlist(self, key):
        "Returns an empty list if the requested data doesn't exist"
        try:
            return dict.__getitem__(self, key)
        except KeyError:
            return []

    def setlist(self, key, list_):
        dict.__setitem__(self, key, list_)

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def setlistdefault(self, key, default_list=()):
        if key not in self:
            self.setlist(key, default_list)
        return self.getlist(key)

    def appendlist(self, key, value):
        "Appends an item to the internal list associated with key"
        self.setlistdefault(key, [])
        dict.__setitem__(self, key, self.getlist(key) + [value])

    def items(self):
        """
        Returns a list of (key, value) pairs, where value is the last item in
        the list associated with the key.
        """
        return [(key, self[key]) for key in self.keys()]

    def lists(self):
        "Returns a list of (key, list) pairs."
        return dict.items(self)

    def values(self):
        "Returns a list of the last value on every key list."
        return [self[key] for key in self.keys()]

    def copy(self):
        "Returns a copy of this object."
        return self.__deepcopy__()

    def update(self, *args, **kwargs):
        "update() extends rather than replaces existing key lists. Also accepts keyword args."
        if len(args) > 1:
            raise TypeError("update expected at most 1 arguments, got %d" % len(args))
        if args:
            other_dict = args[0]
            if isinstance(other_dict, MultiValueDict):
                for key, value_list in other_dict.lists():
                    self.setlistdefault(key, []).extend(value_list)
            else:
                try:
                    for key, value in other_dict.items():
                        self.setlistdefault(key, []).append(value)
                except TypeError:
                    raise ValueError("MultiValueDict.update() takes either a MultiValueDict or dictionary")
        for key, value in six.iteritems(kwargs):
            self.setlistdefault(key, []).append(value)


class SiteNode(object):
    """Class to represent a site node (page, image or any other file)"""

    def __init__(self, url):
        warnings.warn(
            "scrapy.utils.datatypes.SiteNode is deprecated "
            "and will be removed in future releases.",
            category=ScrapyDeprecationWarning,
            stacklevel=2
        )

        self.url = url
        self.itemnames = []
        self.children = []
        self.parent = None

    def add_child(self, node):
        self.children.append(node)
        node.parent = self

    def to_string(self, level=0):
        s = "%s%s\n" % ('  '*level, self.url)
        if self.itemnames:
            for n in self.itemnames:
                s += "%sScraped: %s\n" % ('  '*(level+1), n)
        for node in self.children:
            s += node.to_string(level+1)
        return s


class CaselessDict(dict):

    __slots__ = ()

    def __init__(self, seq=None):
        super(CaselessDict, self).__init__()
        if seq:
            self.update(seq)

    def __getitem__(self, key):
        return dict.__getitem__(self, self.normkey(key))

    def __setitem__(self, key, value):
        dict.__setitem__(self, self.normkey(key), self.normvalue(value))

    def __delitem__(self, key):
        dict.__delitem__(self, self.normkey(key))

    def __contains__(self, key):
        return dict.__contains__(self, self.normkey(key))
    has_key = __contains__

    def __copy__(self):
        return self.__class__(self)
    copy = __copy__

    def normkey(self, key):
        """Method to normalize dictionary key access"""
        return key.lower()

    def normvalue(self, value):
        """Method to normalize values prior to be setted"""
        return value

    def get(self, key, def_val=None):
        return dict.get(self, self.normkey(key), self.normvalue(def_val))

    def setdefault(self, key, def_val=None):
        return dict.setdefault(self, self.normkey(key), self.normvalue(def_val))

    def update(self, seq):
        seq = seq.items() if isinstance(seq, Mapping) else seq
        iseq = ((self.normkey(k), self.normvalue(v)) for k, v in seq)
        super(CaselessDict, self).update(iseq)

    @classmethod
    def fromkeys(cls, keys, value=None):
        return cls((k, value) for k in keys)

    def pop(self, key, *args):
        return dict.pop(self, self.normkey(key), *args)


class MergeDict(object):
    """
    A simple class for creating new "virtual" dictionaries that actually look
    up values in more than one dictionary, passed in the constructor.

    If a key appears in more than one of the given dictionaries, only the
    first occurrence will be used.
    """
    def __init__(self, *dicts):
        if not six.PY2:
            warnings.warn(
                "scrapy.utils.datatypes.MergeDict is deprecated in favor "
                "of collections.ChainMap (introduced in Python 3.3)",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
        self.dicts = dicts

    def __getitem__(self, key):
        for dict_ in self.dicts:
            try:
                return dict_[key]
            except KeyError:
                pass
        raise KeyError

    def __copy__(self):
        return self.__class__(*self.dicts)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def getlist(self, key):
        for dict_ in self.dicts:
            if key in dict_.keys():
                return dict_.getlist(key)
        return []

    def items(self):
        item_list = []
        for dict_ in self.dicts:
            item_list.extend(dict_.items())
        return item_list

    def has_key(self, key):
        for dict_ in self.dicts:
            if key in dict_:
                return True
        return False

    __contains__ = has_key

    def copy(self):
        """Returns a copy of this object."""
        return self.__copy__()


class LocalCache(collections.OrderedDict):
    """Dictionary with a finite number of keys.

    Older items expires first.

    """

    def __init__(self, limit=None):
        super(LocalCache, self).__init__()
        self.limit = limit

    def __setitem__(self, key, value):
        while len(self) >= self.limit:
            self.popitem(last=False)
        super(LocalCache, self).__setitem__(key, value)


class SequenceExclude(object):
    """Object to test if an item is NOT within some sequence."""

    def __init__(self, seq):
        self.seq = seq

    def __contains__(self, item):
        return item not in self.seq
