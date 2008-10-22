from scrapy.item.adaptors import AdaptorPipe as BaseAdaptorPipe
from scrapy.utils.serialization import serialize

class DuplicatedAdaptorName(Exception): pass

class _Adaptor(object):
    """
    Adaptors instances should be instantiated and used only
    inside the AdaptorPipe.
    """
    def __init__(self, function, match_function):
        self.basefunction = function
        self.match_function = match_function
    def __repr__(self):
        return self.basefunction.func_name
    def __call__(self, *args):
        return self.basefunction(*args)
        
class AdaptorPipe(BaseAdaptorPipe):

    def __init__(self, attribute_names, adaptors=None):
        """
        If "adaptors" is given, constructs pipeline from this.
        "adaptors" is an ordered tuple of 2-elements tuples, each of which
        has the same parameters you give to the insertadaptor method, except 
        'after' and 'before', because you define the adaptors order in the tuple.
        Example:
        (
          (my_function, lambda x: x in my_list)
          ...
        )
        """
        self.__attribute_names = [ n for n in attribute_names ]
        self.__adaptorspipe = []
        self.pipes = {}
        if adaptors:
            for entry in adaptors:
                self.insertadaptor(compile_pipe=False, *entry)
            self._compile_pipe()

    @property
    def adaptors_names(self):
        _adaptors = []
        for a in self.__adaptorspipe:
            _adaptors.append(a.basefunction.func_name)
        return _adaptors
    
    def insertadaptor(self, function, match_function=lambda x: True, compile_pipe=True, after=None, before=None):
        """
        Inserts a "function" as an adaptor that will apply when match_function returns True (by
        default always apply)
        If "after" is given, inserts the adaptor after the already inserted adaptor
        of the name given in this parameter, If "before" is given, inserts it before
        the adaptor of the given name. "name" is the name of the adaptor.
        """
        if function.func_name in self.adaptors_names:
            raise DuplicatedAdaptorName(function.func_name)
        else:
            adaptor = _Adaptor(function, match_function)
            #by default append adaptor at end of pipe
            pos = len(self.adaptors_names)
            if after:
                pos = self.adaptors_names.index(after) + 1
            elif before:
                pos = self.adaptors_names.index(before)
            self.__adaptorspipe.insert(pos, adaptor)
            if compile_pipe:
                self._compile_pipe()
            return pos

    def removeadaptor(self, adaptorname):
        pos = self.adaptors_names.index(adaptorname)
        self.__adaptorspipe.pop(pos)
        self._compile_pipe()

    def _compile_pipe(self):
        for attrname in self.__attribute_names:
            adaptors_pipe = []
            for adaptor in self.__adaptorspipe:
                if adaptor.match_function(attrname):
                    adaptors_pipe.append(adaptor)
            self.pipes[attrname] = adaptors_pipe

    def __repr__(self):
        return serialize(self.pipes, "pprint")