import re

class DuplicatedAdaptorName(Exception):
    def __init__(self, name):
        self.__name = name
    def __str__(self):
        return name

class Adaptor(object):
    """
    Adaptors instances should be instantiated and used only
    inside the AdaptorPipe.
    """
    def __init__(self, function, name, attribute_re=None):
        self.name = name
        self.basefunction = function
        if not attribute_re:
            attribute_re = ".*"
        self.attribute_re = re.compile(attribute_re)
    def function(self, value, **pipeargs):
        return self.basefunction(value, **pipeargs)
        
class AdaptorPipe:
    def __init__(self, define_from=None, adaptorclass=None):
        """
        If "define_from" is given, constructs pipeline from this.
        "define_from" is an ordered tuple of triplets, each of which
        has the attribute name regex, the adaptor name, and the module
        path to the adaptor function. Example:
        (
          ("url", "remove_entities", "scrapy.utils.markup.remove_entities")
          (".*", "replace_tags", "scrapy.utils.markup.replace_tags")
          ...
        )
        """
        self.__adaptorspipe = []
        self.__adaptorclass = adaptorclass or Adaptor
    @property
    def adaptors_names(self):
        _adaptors = []
        for a in self.__adaptorspipe:
            _adaptors.append(a.name)
        return _adaptors
    
    def insertadaptor(self, function, name, attrs_re=None, after=None, before=None):
        """
        Inserts a "function" as an adaptor that will apply for attribute names
        which matches "attrs_re" regex, after adaptor of name "after", or before
        adaptor of name "before". The "function" must always have a **keyword
        argument to ignore unused keywords. "name" is the name of the adaptor.
        """
        if name in self.adaptors_names:
            raise DuplicatedAdaptorName(name)
        else:
            adaptor = self.__adaptorclass(function, name, attrs_re)
            #by default append adaptor at end of pipe
            pos = len(self.adaptors_names)
            if after:
                pos = self.adaptors_names.index(after) + 1
            elif before:
                pos = self.adaptors_names.index(before)
            self.__adaptorspipe.insert(pos, adaptor)
            return pos

    def execute(self, attrname, value, **pipeargs):
        """
        Execute pipeline for attribute name "attrname" and value "value".
        Pass the given pipeargs to each adaptor function in the pipe.
        """
        for adaptor in self.__adaptorspipe:
            if adaptor.attribute_re.search(attrname):
                value = adaptor.function(value, **pipeargs)
        return value