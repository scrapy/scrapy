"""
This module contains data types used by Scrapy which are not included in the
Python Standard Library.

This module must not depend on any module outside the Standard Library.
"""

import copy
import gzip
import Queue
import bisect
from cStringIO import StringIO

class MergeDict(object):
    """
    A simple class for creating new "virtual" dictionaries that actualy look
    up values in more than one dictionary, passed in the constructor.
    """
    def __init__(self, *dicts):
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
        for dict in self.dicts:
            try:
                return dict.getlist(key)
            except KeyError:
                pass
        raise KeyError

    def items(self):
        item_list = []
        for dict in self.dicts:
            item_list.extend(dict.items())
        return item_list

    def has_key(self, key):
        for dict in self.dicts:
            if key in dict:
                return True
        return False

    __contains__ = has_key

    def copy(self):
        """ returns a copy of this object"""
        return self.__copy__()

class SortedDict(dict):
    "A dictionary that keeps its keys in the order in which they're inserted."
    def __init__(self, data=None):
        if data is None: 
            data = {}
        dict.__init__(self, data)
        self.keyOrder = data.keys()

    def __setitem__(self, key, value):
        dict.__setitem__(self, key, value)
        if key not in self.keyOrder:
            self.keyOrder.append(key)

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        self.keyOrder.remove(key)

    def __iter__(self):
        for k in self.keyOrder:
            yield k

    def items(self):
        return zip(self.keyOrder, self.values())

    def iteritems(self):
        for key in self.keyOrder:
            yield key, dict.__getitem__(self, key)

    def keys(self):
        return self.keyOrder[:]

    def iterkeys(self):
        return iter(self.keyOrder)

    def values(self):
        return [dict.__getitem__(self, k) for k in self.keyOrder]

    def itervalues(self):
        for key in self.keyOrder:
            yield dict.__getitem__(self, key)

    def update(self, dict):
        for k, v in dict.items():
            self.__setitem__(k, v)

    def setdefault(self, key, default):
        if key not in self.keyOrder:
            self.keyOrder.append(key)
        return dict.setdefault(self, key, default)

    def value_for_index(self, index):
        "Returns the value of the item at the given zero-based index."
        return self[self.keyOrder[index]]

    def insert(self, index, key, value):
        "Inserts the key, value pair before the item with the given index."
        if key in self.keyOrder:
            n = self.keyOrder.index(key)
            del self.keyOrder[n]
            if n < index: 
                index -= 1
        self.keyOrder.insert(index, key)
        dict.__setitem__(self, key, value)

    def copy(self):
        "Returns a copy of this object."
        # This way of initializing the copy means it works for subclasses, too.
        obj = self.__class__(self)
        obj.keyOrder = self.keyOrder
        return obj

    def __repr__(self):
        """
        Replaces the normal dict.__repr__ with a version that returns the keys
        in their sorted order.
        """
        return '{%s}' % ', '.join(['%r: %r' % (k, v) for k, v in self.items()])

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

class DotExpandedDict(dict):
    """
    A special dictionary constructor that takes a dictionary in which the keys
    may contain dots to specify inner dictionaries. It's confusing, but this
    example should make sense.

    >>> d = DotExpandedDict({'person.1.firstname': ['Simon'], \
            'person.1.lastname': ['Willison'], \
            'person.2.firstname': ['Adrian'], \
            'person.2.lastname': ['Holovaty']})
    >>> d
    {'person': {'1': {'lastname': ['Willison'], 'firstname': ['Simon']}, '2': {'lastname': ['Holovaty'], 'firstname': ['Adrian']}}}
    >>> d['person']
    {'1': {'lastname': ['Willison'], 'firstname': ['Simon']}, '2': {'lastname': ['Holovaty'], 'firstname': ['Adrian']}}
    >>> d['person']['1']
    {'lastname': ['Willison'], 'firstname': ['Simon']}

    # Gotcha: Results are unpredictable if the dots are "uneven":
    >>> DotExpandedDict({'c.1': 2, 'c.2': 3, 'c': 1})
    {'c': 1}
    """
    def __init__(self, key_to_list_mapping):
        for k, v in key_to_list_mapping.items():
            current = self
            bits = k.split('.')
            for bit in bits[:-1]:
                current = current.setdefault(bit, {})
            # Now assign value to current position
            try:
                current[bits[-1]] = v
            except TypeError: # Special-case if current isn't a dict.
                current = {bits[-1] : v}

class FileDict(dict):
    """
    A dictionary used to hold uploaded file contents. The only special feature
    here is that repr() of this object won't dump the entire contents of the
    file to the output. A handy safeguard for a large file upload.
    """
    def __repr__(self):
        if 'content' in self:
            d = dict(self, content='<omitted>')
            return dict.__repr__(d)
        return dict.__repr__(self)

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


class PriorityQueue(Queue.Queue):

    def __len__(self):
        return self.qsize()

    def _init(self, maxsize):
        self.maxsize = maxsize
        # Python 2.5 uses collections.deque, but we can't because
        # we need insert(pos, item) for our priority stuff
        self.queue = []

    def put(self, item, priority=0, block=True, timeout=None):
        """Puts an item onto the queue with a numeric priority (default is zero).
        
        Note that we are "shadowing" the original Queue.Queue put() method here.
        """
        Queue.Queue.put(self, (priority, item), block, timeout)

    def _put(self, item):
        """Override of the Queue._put to support prioritisation."""
        # Priorities must be integers!
        priority = int(item[0])

        # Using a tuple (priority+1,) finds us the correct insertion
        # position to maintain the existing ordering.
        self.queue.insert(bisect.bisect_left(self.queue, (priority+1,)), item)

    def _get(self):
        """Override of Queue._get().  Strips the priority."""
        return self.queue.pop(0)


class PriorityStack(PriorityQueue):
    def _put(self, item):
        priority = int(item[0])
        self.queue.insert(bisect.bisect_left(self.queue, (priority,)), item)

class gzStringIO:
    """a file like object, similar to StringIO, but gzip-compressed."""
    def __init__(self, data, compress_level = 9, filename = ""):
        self._s = StringIO()
        g = gzip.GzipFile(filename, "wb", compress_level, self._s)
        g.write(data)
        g.flush()
        g.close()
    def read(self):
        return self._s.getvalue()

