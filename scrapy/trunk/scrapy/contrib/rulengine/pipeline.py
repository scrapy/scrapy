"""
Represent the pipepline of execution to the rules engine.
"""
from scrapy.core import log
from scrapy.contrib.rulengine.exceptions import RulesNotLoaded

from scrapy.contrib.rulengine import rules

class RulesPipeline(object):

    rulesLoaded = []
    loaded = False
    
    def __init__(self, wresponse):
        """
        wresponse: is a response wrapper object that contain the response.
        """
        self.__rules = []
        self._responsewrapper = wresponse
    
    @staticmethod
    def loadRules():
        RulesPipeline.loaded = True
        rules.load()
        try:
            for rulename in rules.enabled.keys():
                ldr_msg = 'Loading ... %s' % rulename
                ruleClass = rules.enabled[rulename]
                RulesPipeline.rulesLoaded.append(ruleClass())
                log.msg(ldr_msg)
                print ldr_msg
        except Exception, e:
            RulesPipeline.loaded = False
            RulesPipeline.rulesLoaded = []
            log.msg(e)
            print e

    def execute(self):
        """
        Return a dictionary that conatins all the rules executed.
        """
        if RulesPipeline.loaded:
            rules_loaded = RulesPipeline.rulesLoaded
            info_dict = {}
            info_dict['rules_executed'] = {}
            total = 0.0
            for rule in rules_loaded:
                rule.responsewrapper = self._responsewrapper
                rule_result = rule.check()
                total += rule_result
                info_dict['rules_executed'][rule.__class__.__name__] = rule_result
            return info_dict
        else:
            raise RulesNotLoaded, 'Problems loading the rules.'
