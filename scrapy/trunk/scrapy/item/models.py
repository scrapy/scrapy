from scrapy.item.adaptors import AdaptorPipe

def extract(value):
    if hasattr(value, 'extract'):
        value = value.extract()
    return value
    
standardpipe = AdaptorPipe()
standardpipe.insertadaptor(extract, "extract")

class ScrapedItem(object):
    """
    This is the base class for all scraped items.

    The only required attributes are:
    * guid (unique global indentifier)
    * url (URL where that item was scraped from)
    """
    adaptors_pipe = standardpipe
    
    def set_adaptors_pipe(adaptors_pipes):
        ScrapedItem.adaptors_pipes = adaptors_pipes

    def attribute(self, attrname, value, **pipeargs):
        value =ScrapedItem.adaptors_pipe.execute(attrname, value, **pipeargs)
        if not hasattr(self, attrname):
            setattr(self, attrname, value)