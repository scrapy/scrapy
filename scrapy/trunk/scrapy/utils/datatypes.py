"""
This module contains data types used by Scrapy which are not included in the
Python Standard Library.

This module must not depend on any module outside the Standard Library.
"""

import time
import copy
from heapq import heappush, heappop

class MultiValueDictKeyError(KeyError):
    pass

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
            raise MultiValueDictKeyError, "Key %r not found in %r" % (key, self)
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
            raise TypeError, "update expected at most 1 arguments, got %d" % len(args)
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
                    raise ValueError, "MultiValueDict.update() takes either a MultiValueDict or dictionary"
        for key, value in kwargs.iteritems():
            self.setlistdefault(key, []).append(value)

class Sitemap(object):
    """Sitemap class is used to build a map of the traversed pages"""

    def __init__(self):
        self._nodes = {}
        self._roots = []

    def add_node(self, url, parent_url):
        if not url in self._nodes:
            parent = self._nodes.get(parent_url, None)
            node = SiteNode(url)
            self._nodes[url] = node
            if parent:
                parent.add_child(node)
            else:
                self._roots.append(node)

    def add_item(self, url, item):
        if url in self._nodes:
            self._nodes[url].itemnames.append(str(item))
    
    def to_string(self):
        s = ''.join([n.to_string(0) for n in self._roots])
        return s

class SiteNode(object):
    """Class to represent a site node (page, image or any other file)"""

    def __init__(self, url):
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
    def __init__(self, other=None):
        if other:
            # Doesn't do keyword args
            if isinstance(other, dict):
                for k, v in other.items():
                    dict.__setitem__(self, self.normkey(k), v)
            else:
                for k, v in other:
                    dict.__setitem__(self, self.normkey(k), v)

    def __getitem__(self, key):
        return dict.__getitem__(self, self.normkey(key))

    def __setitem__(self, key, value):
        dict.__setitem__(self, self.normkey(key), value)

    def __delitem__(self, key):
        dict.__delitem__(self, self.normkey(key))

    def __contains__(self, key):
        return dict.__contains__(self, self.normkey(key))

    def normkey(self, key):
        return key.lower()

    def has_key(self, key):
        return dict.has_key(self, self.normkey(key))

    def get(self, key, def_val=None):
        return dict.get(self, self.normkey(key), def_val)

    def setdefault(self, key, def_val=None):
        return dict.setdefault(self, self.normkey(key), def_val)

    def update(self, other):
        for k, v in other.items():
            dict.__setitem__(self, self.normkey(k), v)

    def fromkeys(self, iterable, value=None):
        d = CaselessDict()
        for k in iterable:
            dict.__setitem__(d, self.normkey(k), value)
        return d

    def pop(self, key, def_val=None):
        return dict.pop(self, self.normkey(key), def_val)

class PriorityQueue(object):
    """A simple priority queue"""

    def __init__(self):
        self.items = []

    def push(self, item, priority=0):
        heappush(self.items, (priority, time.time(), item))

    def pop(self):
        priority, _, item = heappop(self.items)
        return item, priority

    def __len__(self):
        return len(self.items)

    def __iter__(self):
        return ((item, priority) for priority, _, item in self.items)

    def __nonzero__(self):
        return bool(self.items)

class PriorityStack(PriorityQueue):
    """A simple priority stack which is similar to PriorityQueue but pops its
    items in reverse order (for the same priority)"""

    def push(self, item, priority=0):
        heappush(self.items, (priority, -time.time(), item))

