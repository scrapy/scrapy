from scrapy.conf import settings
from scrapy.item.adaptors import AdaptorPipe

class ScrapedItem(object):
    """
    This is the base class for all scraped items.
    'guid' attribute is required, and is an attribute
    that identifies uniquely the given scraped item.
    """

    def __init__(self, data=None):
        """
        A ScrapedItem can be initialised with a dictionary that will be
        squirted directly into the object.
        """
        self._adaptors_dict = {}

        if isinstance(data, dict):
            for attr, value in data.iteritems():
                setattr(self, attr, value)
        elif data is not None:
            raise UsageError("Initialize with dict, not %s" % data.__class__.__name__)

    def __repr__(self):
        """
        Generate the following format so that items can be deserialized
        easily: ClassName({'attrib': value, ...})
        """
        reprdict = dict(items for items in self.__dict__.iteritems() if not items[0].startswith('_'))
        return "%s(%s)" % (self.__class__.__name__, repr(reprdict))

    def __sub__(self, other):
        raise NotImplementedError

    def set_adaptors(self, adaptors_dict):
        """
        Set the adaptors to use for this item. Receives a dict of the adaptors
        desired for each attribute and returns the item itself.
        """
        _adaptors_dict = dict((attrib, AdaptorPipe(pipe)) for attrib, pipe in adaptors_dict.items() if hasattr(pipe, '__iter__'))
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

    def attribute(self, attrname, value, override=False, add=False, **kwargs):
        """
        Set the given value to the provided attribute (`attrname`) by filtering it
        through its adaptor pipeline first (if it has any).

        If the attribute has been already set, it won't be overwritten unless
        `override` is True.
        If there was an old value and `add` is True (but `override` isn't), `value`
        will be appended/extended (depending on its type), to the old value, as long as
        the old value is a list.
        If both of the values are strings they will be joined by using the `add` delimiter
        (which may be a string, or True, in which case '' will be used as the delimiter).

        The kwargs parameter is passed to the adaptors pipeline, which manages to transmit
        it to the adaptors themselves.
        """
        pipe = self._adaptors_dict.get(attrname)
        old_value = getattr(self, attrname, None)

        if pipe:
            value = pipe(value, **kwargs)

        if old_value:
            if override:
                setattr(self, attrname, value)
            elif add:
                if hasattr(old_value, '__iter__'):
                    if hasattr(value, '__iter__'):
                        self.__dict__[attrname].extend(list(value))
                    else:
                        self.__dict__[attrname].append(value)
                elif isinstance(old_value, basestring) and isinstance(value, basestring):
                    delimiter = add if isinstance(add, basestring) else ''
                    setattr(self, attrname, '%s%s%s' % (old_value, delimiter, value))
        else:
            setattr(self, attrname, value)


class ItemDelta(object):
    pass
