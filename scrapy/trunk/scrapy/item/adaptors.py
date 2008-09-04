import re
from traceback import format_exc
from scrapy.core import log

class DuplicatedAdaptorName(Exception): pass

class Adaptor(object):
    """
    Adaptors instances should be instantiated and used only
    inside the AdaptorPipe.
    """
    def __init__(self, function, name, attribute_re=None, attribute_list=None):
        self.name = name
        self.basefunction = function
        self.attribute_re = re.compile(attribute_re) if attribute_re else None
        self.attribute_list = attribute_list or []
    def function(self, value, **pipeargs):
        return self.basefunction(value, **pipeargs)
        
class AdaptorPipe:

    def __init__(self, adaptors=None, adaptorclass=None):
        """
        If "adaptors" is given, constructs pipeline from this.
        "define_from" is an ordered tuple of 4-elements tuples, each of which
        has the same parameters you give to the insertadaptor method, except 
        'after' and 'before', because you define the adaptors order in the tuple.
        . Example:
        (
          ("my_function", "my_function", None, "name")
          ...
        )
        """
        self.__adaptorspipe = []
        self.__adaptorclass = adaptorclass or Adaptor
        if adaptors:
            for entry in adaptors:
                self.insertadaptor(*entry)

    @property
    def adaptors_names(self):
        _adaptors = []
        for a in self.__adaptorspipe:
            _adaptors.append(a.name)
        return _adaptors
    
    def insertadaptor(self, function, name, attrs_re=None, attrs_list=None, after=None, before=None):
        """
        Inserts a "function" as an adaptor that will apply for attribute names
        which matches regex given in "attrs_re" (None matches all), or are included in "attrs_list" list.
        If both, attrs_re and attrs_list are given, apply both. Else if only one is given, apply those.
        Else, all attributes will match.
        
        If "after" is given, inserts the adaptor after the already inserted adaptor
        of the name given in this parameter, If "before" is given, inserts it before
        the adaptor of the given name. The "function" must always have a **keyword
        argument to ignore unused keywords. "name" is the name of the adaptor.
        """
        if name in self.adaptors_names:
            raise DuplicatedAdaptorName(name)
        else:
            adaptor = self.__adaptorclass(function, name, attrs_re, attrs_list)
            #by default append adaptor at end of pipe
            pos = len(self.adaptors_names)
            if after:
                pos = self.adaptors_names.index(after) + 1
            elif before:
                pos = self.adaptors_names.index(before)
            self.__adaptorspipe.insert(pos, adaptor)
            return pos

    def execute(self, attrname, value, debug=False, **pipeargs):
        """
        Execute pipeline for attribute name "attrname" and value "value".
        Pass the given pipeargs to each adaptor function in the pipe.
        """
        for adaptor in self.__adaptorspipe:
            adapt = False
            if adaptor.attribute_re:
                if adaptor.attribute_re.search(attrname):
                    if adaptor.attribute_list:
                        adapt = attrname in adaptor.attribute_list
                    else:
                        adapt = True
            elif adaptor.attribute_list:
                adapt = attrname in adaptor.attribute_list
            else:
                adapt = True
            if adapt:
                try:
                    if debug:
                        print "pipeargs: %s" % repr(pipeargs)
                        print "  %07s | input >" % adaptor.name, repr(value)
                    value = adaptor.function(value, **pipeargs)
                    if debug:
                        print "  %07s | output>" % adaptor.name, repr(value)

                except Exception, e:
                    print "Error in '%s' adaptor. Traceback text:" % adaptor.name
                    print format_exc()
                    return
                    
        return value
