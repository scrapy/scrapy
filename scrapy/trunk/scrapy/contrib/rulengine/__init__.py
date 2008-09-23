"""
Here put the rules that the rules engine / pipline will take to process it.
"""
from scrapy.core.exceptions import NotConfigured
from scrapy.utils.misc import load_class
from scrapy import log 
from scrapy.conf import settings

class Rule(object):
    """
    Interface of the Rules. 
    Implement this class to create a new rule.
    """
    def __init__(self, wresponse=None):
        self.__responsewrapper = wresponse
    
    def __getresponsewrapper(self):
        return self.__responsewrapper
    def __setresponsewrapper(self, wresponse):
        self.__responsewrapper = wresponse

    responsewrapper = property(__getresponsewrapper, __setresponsewrapper)
    
    def check(self):
        result = 0.0
        if self.responsewrapper:
            result = self.holds()
            if result < 0 or result > 1:
                raise ValueError, "Value must be between 0 and 1."
        return result

    def holds(self):
        """
        User of this class must override this method.
        Put here the conditions that must be satisfied by the rule.
        The return value must be a number between 0.0 and 1.0.
        """
        return 0.0

class RulesManager(object):
    """
    This class contains the RulesManager  which takes care of loading and
    keeping track of all enabled rules. It also contains an instantiated
    RulesManager (rules) to be used as singleton.
    The RulesManager contains the rules classes, not instances of the rules 
    classes, this approach give us more flexiblility in our Rules Engine.
    """

    def __init__(self):
        self.loaded = False
        self.enabled = {}

    def load(self):
        """
        Load enabled extensions in settings module
        """
        
        self.loaded = False
        self.enabled.clear()
        
        for extension_path in settings.getlist('SIMPAGES_RULES'):
            cls = load_class(extension_path)
            self.enabled[cls.__name__] = cls
                
        self.loaded = True
    
    def reload(self):
        self.load()

rules = RulesManager()




