"""
This module contains some extra base models for scraped items which could be
useful in some Scrapy implementations
"""

import hashlib

from scrapy.item import ScrapedItem
from scrapy.core.exceptions import UsageError, DropItem

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
    def process_item(self, domain, response, item):
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
    
    def __init__(self, data=None):
        """
        A scraped item can be initialised with a dictionary that will be
        squirted directly into the object.
        """
        if isinstance(data, dict):
            for attr, value in data.iteritems():
                setattr(self, attr, value)
        elif data is not None:
            raise UsageError("Initialize with dict, not %s" % data.__class__.__name__)

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
        if other:
            return self.version == other.version
        
    def __ne__(self, other):
        return self.version != other.version
        
    def __repr__(self):
        # Generate this format so that it can be deserialized easily:
        # ClassName({...})
        reprdict = {}
        for k, v in self.__dict__.iteritems():
            if not k.startswith('_'):
                reprdict[k] = v
        return "%s(%s)" % (self.__class__.__name__, repr(reprdict))

    def __str__(self) :
        return "%s: GUID=%s, url=%s" % ( self.__class__.__name__ , self.guid, self.url )
            
    def validate(self):
        """Method used to validate item attributes data"""
        if not self.guid:
            raise ValidationError('A guid is required')

    def copy(self):
        """Create a new ScrapedItem object based on the current one"""
        import copy
        return copy.deepcopy(self)

    @property
    def version(self):
        """
        Return a (cached) 40 char hash of all the item attributes.

        WARNING: This cached version won't work if mutable products are
        modified directly like:

        item.features.append('feature')
        """
        if self._version:
            return self._version
        hash_ = hashlib.sha1()
        hash_.update("".join(["".join([n, str(v)]) for n,v in sorted(self.__dict__.iteritems())]))
        return hash_.hexdigest()
