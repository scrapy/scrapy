from traceback import format_exc
from scrapy.conf import settings

class AdaptorDict(dict):
    """
    Class that represents an item's attribute pipeline.

    This class contains a dictionary of attributes, matched with a list
    of adaptors to be run for filtering the input before storing.
    """

    def execute(self, attrname, value, debug=False):
        """
        Execute pipeline for attribute name "attrname" and value "value".
        """
        debug = debug or all([settings.getbool('LOG_ENABLED'), settings.get('LOGLEVEL') == 'TRACE'])

        for adaptor in self.get(attrname, []):
            name = adaptor.__class__.__name__ if hasattr(adaptor, '__class__') else adaptor.__name__
            try:
                if debug:
                    print "  %07s | input >" % name, repr(value)
                value = adaptor(value)
                if debug:
                    print "  %07s | output >" % name, repr(value)
       
            except Exception:
                print "Error in '%s' adaptor. Traceback text:" % name
                print format_exc()
                return
        
        return value

