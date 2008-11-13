import types

from traceback import format_exc
from scrapy import log
from scrapy.conf import settings
from scrapy.core.exceptions import NotConfigured

class ItemAttribute(object):
    def __init__(self, attrib_name, attrib_type, adaptor=None):
        self.attrib_name = attrib_name
        self.attrib_type = attrib_type
        self.adaptor = adaptor

    def adapt(self, value, **kwargs):
        debug = kwargs.get('debug') or all([settings.getbool('LOG_ENABLED'), settings.get('LOGLEVEL') == 'TRACE'])
        if not self.adaptor:
            if debug:
                log.msg('No adaptor defined for attribute %s.' % self.attrib_name, log.WARNING)
            return value

        try:
            if debug:
                print "  %07s | input >" % self.attrib_name, repr(value)
            value = self.adaptor(value, **kwargs)
            if debug:
                print "  %07s | output >" % self.attrib_name, repr(value)
        
        except Exception:
            print "Error in '%s' adaptor. Traceback text:" % name
            print format_exc()
            self.value = None
            return False
        
        return value
        
    def check(self, value):
        if not self.attrib_name:
            raise NotConfigured('You must define "attrib_name" attribute in order to use an ItemAttribute')

        if not self.attrib_type:
            raise NotConfigured('You must define "attrib_type" attribute in order to use an ItemAttribute')
        else:
            if hasattr(self.attrib_type, '__iter__'):
                if not hasattr(value, '__iter__'):
                    raise TypeError('Attribute "%s" must be a sequence' % self.attrib_name)
                iter_type = self.attrib_type[0]
                for i in value:
                    if not isinstance(i, iter_type):
                        raise TypeError('Attribute "%s" cannot contain %s, only %s' % (self.name, i.__class__.__name__, iter_type.__name__))
            else:
                if not isinstance(value, self.attrib_type):
                    raise TypeError('Attribute "%s" must be %s, not %s' % (self.attrib_name, self.attrib_type.__name__, value.__class__.__name__))
        return True

class ItemDelta(object):
    pass

class ScrapedItem(object):
    """
    This is the base class for all scraped items.
    'guid' attribute is required, and is an attribute
    that identifies uniquely the given scraped item.
    """

    ATTRIBUTES = { 'guid': ItemAttribute(attrib_name='guid', attrib_type=basestring) }
    _override_adaptors = { }

    def __setattr__(self, attr, value):
        if value is None:
            self.__dict__.pop(attr, None)
            return

        if attr in self.ATTRIBUTES:
            self.ATTRIBUTES[attr].check(value)
        self.__dict__[attr] = value

    def set_adaptor(self, attrname, adaptor):
        if attrname in self.ATTRIBUTES and callable(adaptor):
            self._override_adaptors[attrname] = adaptor
        
    def attribute(self, attrname, val, **kwargs):
        if not attrname in self.ATTRIBUTES and not attrname.startswith('_'):
            raise AttributeError('Attribute "%s" is not a valid attribute name. You must add it to %s.ATTRIBUTES' % (attrname, self.__class__.__name__))

        override = kwargs.pop('override', False)
        add = kwargs.pop('add', False)
        adaptor = self._override_adaptors.get(attrname) or self.ATTRIBUTES[attrname].adapt

        val = adaptor(val, **kwargs)
        if not val is None:
            curr_val = getattr(self, attrname, None)
            if not curr_val:
                setattr(self, attrname, val)
            else:
                if override:
                    setattr(self, attrname, val)
                elif add and all(hasattr(var, '__iter__') for var in (curr_val, val)):
                    newval = []
                    newval.extend(curr_val)
                    newval.extend(val)
                    setattr(self, attrname, newval)

    def __sub__(self, other):
        raise NotImplementedError

