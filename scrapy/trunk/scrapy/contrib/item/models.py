"""
This module contains some extra base models for scraped items which could be
useful in some Scrapy implementations
"""

import hashlib

from pydispatch import dispatcher
from pprint import PrettyPrinter

from scrapy.item import ScrapedItem, ItemDelta
from scrapy.item.adaptors import AdaptorPipe
from scrapy.spider import spiders
from scrapy.core import signals
from scrapy.core.exceptions import UsageError, DropItem
from scrapy.utils.python import unique

class ValidationError(DropItem):
    """Indicates a data validation error"""
    def __init__(self,problem,value=None):
        self.problem = problem
        self.value = value

    def __str__(self):
        if self.value is not None:
            return '%s "%s"' % (self.problem, self.value)
        else:
            return '%s' % (self.problem)

class ValidationPipeline(object):
    def process_item(self, domain, item):
        item.validate()
        return item

class RobustScrapedItem(ScrapedItem):
    """
    A more robust scraped item class with a built-in validation mechanism and 
    minimal versioning support
    """

    ATTRIBUTES = {
        'guid': basestring, # a global unique identifier
        'url': basestring,  # the main URL where this item was scraped from
    }

    def __init__(self, data=None, adaptors_dict=None):
        super(RobustScrapedItem, self).__init__(data)
        self.__dict__['_adaptors_dict'] = adaptors_dict or {}
        self.__dict__['_version'] = None

    def __getattr__(self, attr):
        # Return None for valid attributes not set, raise AttributeError for invalid attributes
        # Note that this method is called only when the attribute is not found in 
        # self.__dict__ or the class/instance methods.
        if attr in self.ATTRIBUTES:
            return None
        else:
            raise AttributeError(attr)

    def __setattr__(self, attr, value):
        """
        Set an attribute checking it matches the attribute type declared in self.ATTRIBUTES
        """
        if not attr.startswith('_') and attr not in self.ATTRIBUTES:
            raise AttributeError('Attribute "%s" is not a valid attribute name. You must add it to %s.ATTRIBUTES' % (attr, self.__class__.__name__))

        if value is None:
            self.__dict__.pop(attr, None)
            return

        if attr == '_adaptors_dict':
            return object.__setattr__(self, '_adaptors_dict', value)

        type1 = self.ATTRIBUTES[attr]
        if hasattr(type1, '__iter__'):
            if not hasattr(value, '__iter__'):
                raise TypeError('Attribute "%s" must be a sequence' % attr)
            type2 = type1[0]
            for i in value:
                if not isinstance(i, type2):
                    raise TypeError('Attribute "%s" cannot contain %s, only %s' % (attr, i.__class__.__name__, type2.__name__))
        else:
            if not isinstance(value, type1):
                raise TypeError('Attribute "%s" must be %s, not %s' % (attr, type1.__name__, value.__class__.__name__))

        self.__dict__[attr] = value
        self.__dict__['_version'] = None

    def __delattr__(self, attr):
        """
        Delete an attribute from the ScrapedItem instance if it exists.
        If not, raise an AttributeError.
        """
        if attr in self.__dict__:
            del self.__dict__[attr]
            self.__dict__['_version'] = None
        else:
            raise AttributeError("Attribute '%s' doesn't exist" % attr)

    def __eq__(self, other):
        if isinstance(other, type(self)):
            return self.version == other.version

    def __ne__(self, other):
        return self.version != other.version

    def __sub__(self, other):
        return RobustItemDelta(other, self)

    def __str__(self) :
        return "%s: GUID=%s, url=%s" % ( self.__class__.__name__ , self.guid, self.url )

    def _add_single_attributes(self, attrname, attrtype, attributes):
        raise NotImplementedError('You must override _add_single_attributes method in order to join %s values into a single value.' % attrtype.__name__)

    def attribute(self, attrname, *values, **kwargs):
        """
        Set the provided values to the provided attribute (`attrname`) by filtering them
        through its adaptor pipeline first (if any).

        If the attribute had been already set, it won't be overwritten unless the parameters
        `override` or `add` are True.

        If `override` is True, the old value simply will be replaced with the new one.

        If add is True (and there was an old value, of course), for multivalued attributes the values
        will be appended to the list of the already existing ones.
        For this same situation in single-valued attributes, the method _add_single_attributes will be
        called with the attribute's name and type, and the list of values to join as parameters.

        The kwargs parameter is passed to the adaptors pipeline, which manages to transmit
        it to the adaptors themselves.
        """
        def _clean_values(values):
            ret = []
            for val in values:
                if isinstance(val, tuple):
                    ret.extend(val)
                elif val:
                    ret.append(val)
            return ret

        if not values:
            raise UsageError("You must specify at least one value when setting an attribute")
        if attrname not in self.ATTRIBUTES:
            raise AttributeError('Attribute "%s" is not a valid attribute name. You must add it to %s.ATTRIBUTES' % (attrname, self.__class__.__name__))

        add = kwargs.pop('add', False)
        override = kwargs.pop('override', False)
        unique_vals = kwargs.pop('unique', False)
        old_value = getattr(self, attrname, None)
        if old_value and not any([override, add]):
            return

        attrtype = self.ATTRIBUTES.get(attrname)
        multivalued = isinstance(attrtype, list)
        adaptors_pipe = self._adaptors_dict.get(attrname)
        new_values = [adaptors_pipe(value, kwargs) for value in values] if adaptors_pipe else [values]
        new_values = _clean_values(new_values)

        if old_value and not override:
            if multivalued:
                new_values = old_value + new_values
            else:
                new_values.insert(0, old_value)

        if not multivalued:
            if add and len(new_values) > 1:
                new_values = self._add_single_attributes(attrname, attrtype, new_values)
            else:
                new_values = new_values[0] if new_values else None
        elif multivalued and unique_vals:
            new_values = unique(new_values)

        setattr(self, attrname, new_values)

    def set_attrib_adaptors(self, attrib, pipe):
        """ Set the adaptors (from a list or tuple) to be used for a specific attribute. """
        self._adaptors_dict[attrib] = pipe if isinstance(pipe, AdaptorPipe) else AdaptorPipe(pipe)

    def set_adaptors(self, adaptors_dict):
        """
        Set the adaptors to use for this item. Receives a dict of the adaptors
        desired for each attribute and returns the item itself.
        """
        self._adaptors_dict = {}
        for attrib, pipe in adaptors_dict.items():
            self.set_attrib_adaptors(attrib, pipe)
        return self

    def add_adaptor(self, attrib, adaptor, position=None):
        """
        Add an adaptor for the specified attribute at the given position.
        If position = None, then the adaptor is appended at the end of the pipeline.
        """
        pipe = self._adaptors_dict.get(attrib, AdaptorPipe([]))
        pipe.add_adaptor(adaptor, position)
        self.set_attrib_adaptors(attrib, pipe)

    def validate(self):
        """Method used to validate item attributes data"""
        if not self.guid:
            raise ValidationError('A guid is required')

    @property
    def version(self):
        """
        Return a (cached) 40 char hash of all the item attributes.

        WARNING: This cached version won't work if mutable products are
        modified directly like:

        item.features.append('feature')
        """
        if getattr(self, '_version', None):
            return self._version
        hash_ = hashlib.sha1()
        hash_.update("".join(["".join([n, str(v)]) for n,v in sorted(self.__dict__.iteritems())]))
        return hash_.hexdigest()


class RobustItemDelta(ItemDelta):
    """
    This class represents the difference between
    a pair of RobustScrapedItems.
    """

    def __init__(self, old_item, new_item):
        if not isinstance(old_item, RobustScrapedItem) or \
           not isinstance(new_item, RobustScrapedItem):
            raise TypeError("Both arguments must be RobustScrapedItem instances")

        if old_item.guid != new_item.guid:
            raise AttributeError("Item GUIDs must be equal in order to create a RobustItemDelta object")

        self.old_item = old_item
        self.new_item = new_item
        self.diff = self.do_diff()

    def do_diff(self):
        """
        This method should retreive a dictionary
        containing the changes between both items
        as in this example:

        >>> delta.do_diff()
        >>> {'attrib': {'new': 'New value', 'old': 'Old value'}, # Common attributes
             'attrib2': {'new': 'New value 2', 'old': 'Old value 2'},
             'attrib3': [{'new': 'New list value', 'old': 'Old list value'}, # List attributes
                         {'new': 'New list value 2', 'old': 'Old list value 2'}]}
        """

        if self.old_item == self.new_item:
            return {}

        diff = {}
        for key, value in self.old_item.__dict__.items():
            if key in self.old_item.ATTRIBUTES.keys():
                new_value = getattr(self.new_item, key)
                if value != new_value:
                    diff[key] = {'new': new_value, 'old': value}
        for key, value in self.new_item.__dict__.items():
            if value and key in self.new_item.ATTRIBUTES.keys():
                if not getattr(self.old_item, key):
                    diff[key] = {'new': value, 'old': None}
        return diff

    def __eq__(self, other):
        if isinstance(other, RobustItemDelta):
            if other.old_item == self.old_item and \
               other.new_item == self.new_item and \
               other.diff == self.diff:
                return True
        return False

    def __nonzero__(self):
        return bool(self.diff)

    def __repr__(self):
        if self.diff:
            pp = PrettyPrinter(indent=3)
            return pp.pformat(self.diff)
        else:
            return 'No differences found between the provided items.'

