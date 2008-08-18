class BaseAdaptor(object):
    def function(self, item, value, **pipeargs):
        raise NotImplemented

#default adaptors
class ExtractAdaptor(BaseAdaptor):
    def function(self, item, value, **pipeargs):
        if hasattr(value, 'extract'):
            value = value.extract()
        return value

class ScrapedItem(object):
    """
    This is the base class for all scraped items.

    The only required attributes are:
    * guid (unique global indentifier)
    * url (URL where that item was scraped from)
    """
    adaptors_pipe = [ExtractAdaptor()]
    
    def set_adaptors_pipe(adaptors_pipes):
        ScrapedItem.adaptors_pipes = adaptors_pipes

    def attribute(self, name, value, **pipeargs):

        for adaptor in ScrapedItem.adaptors_pipe:
            value = adaptor.function(self, value, **pipeargs)
        if not hasattr(item, name):
            setattr(item, name, value)