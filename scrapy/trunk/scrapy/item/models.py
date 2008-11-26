from scrapy.conf import settings
from scrapy.item.adaptors import AdaptorPipe

class ScrapedItem(object):
    """
    This is the base class for all scraped items.
    'guid' attribute is required, and is an attribute
    that identifies uniquely the given scraped item.
    """
    _adaptors_dict = {}

    def set_adaptors(self, adaptors_dict):
        """
        Set the adaptors to use for this item. Receives a dict of the adaptors
        desired for each attribute and returns the item itself.
        """
        _adaptors_dict = dict(item for item in adaptors_dict.items() if isinstance(item[1], AdaptorPipe))
        self.__dict__['_adaptors_dict'] = _adaptors_dict
        return self
    
    def set_attrib_adaptors(self, attrib, pipe):
        """ Set the adaptors (from a list or tuple) to be used for a specific attribute. """
        self._adaptors_dict[attrib] = AdaptorPipe(pipe) if hasattr(pipe, '__iter__') else None

    def add_adaptor(self, attrib, adaptor, position=None):
        """
        Add an adaptor for the specified attribute at the given position.
        If position = None, then the adaptor is appended at the end of the pipeline.
        """
        if callable(adaptor):
            pipe = self._adaptors_dict.get(attrib, [])
            if position is None:
                pipe = pipe + [adaptor]
            else:
                pipe.insert(position, adaptor)
            self.set_attrib_adaptors(attrib, pipe)

    def attribute(self, attrname, value, **kwargs):
        override = kwargs.pop('override', False)
        add = kwargs.pop('add', False)
        pipe = self._adaptors_dict.get(attrname)
        if pipe:
            val = pipe(value, **kwargs)
            if val or val is False:
                curr_val = getattr(self, attrname, None)
                if not curr_val:
                    setattr(self, attrname, val)
                else:
                    if override:
                        setattr(self, attrname, val)
                    elif add:
                        if all(isinstance(var, basestring) for var in (curr_val, val)):
                            setattr(self, attrname, '%s\t%s' % (curr_val, val))
                        elif all(hasattr(var, '__iter__') for var in (curr_val, val)):
                            setattr(self, attrname, curr_val + val)
        elif value:
            setattr(self, attrname, value)

    def __sub__(self, other):
        raise NotImplementedError

class ItemDelta(object):
    pass
