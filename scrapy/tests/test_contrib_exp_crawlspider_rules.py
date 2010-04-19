from twisted.trial import unittest

from scrapy.http import HtmlResponse
from scrapy.spider import BaseSpider
from scrapy.contrib_exp.crawlspider.matchers import BaseMatcher
from scrapy.contrib_exp.crawlspider.matchers import UrlMatcher
from scrapy.contrib_exp.crawlspider.matchers import UrlRegexMatcher

from scrapy.contrib_exp.crawlspider.rules import CompiledRule
from scrapy.contrib_exp.crawlspider.rules import Rule
from scrapy.contrib_exp.crawlspider.rules import RulesManager

from functools import partial

class RuleInitializationTest(unittest.TestCase):

    def test_fail_if_rule_null(self):
        # fail on empty rule
        self.failUnlessRaises(ValueError, Rule)
        self.failUnlessRaises(ValueError, Rule,
                                **dict(callback=None, follow=None))
        self.failUnlessRaises(ValueError, Rule,
                                **dict(callback=None, follow=False))

    def test_minimal_arguments_to_instantiation(self):
        # not fail if callback set
        self.failUnless(Rule(callback=lambda: True))
        # not fail if follow set
        self.failUnless(Rule(follow=True))

    def test_validate_default_attributes(self):
        # test null Rule
        rule = Rule(follow=True)
        self.failUnlessEqual(None, rule.matcher)
        self.failUnlessEqual(None, rule.callback)
        self.failUnlessEqual({}, rule.cb_kwargs)
        # follow default False
        self.failUnlessEqual(True, rule.follow)

    def test_validate_attributes_set(self):
        matcher = BaseMatcher()
        callback = lambda: True
        rule = Rule(matcher, callback, True, a=1)
        # test attributes
        self.failUnlessEqual(matcher, rule.matcher)
        self.failUnlessEqual(callback, rule.callback)
        self.failUnlessEqual({'a': 1}, rule.cb_kwargs)
        self.failUnlessEqual(True, rule.follow)

class CompiledRuleInitializationTest(unittest.TestCase):

    def test_fail_on_invalid_matcher(self):
        # pass with valid matcher
        self.failUnless(CompiledRule(BaseMatcher()),
                "Failed CompiledRule instantiation")

        # at least needs valid matcher
        self.assertRaises(AssertionError, CompiledRule, None)
        self.assertRaises(AssertionError, CompiledRule, False)
        self.assertRaises(AssertionError, CompiledRule, True)

    def test_fail_on_invalid_callback(self):
        # pass with valid callback
        callback = lambda: True
        self.failUnless(CompiledRule(BaseMatcher(), callback))
        # pass with callback none
        self.failUnless(CompiledRule(BaseMatcher(), None))

        # assert on invalid callback
        self.assertRaises(AssertionError, CompiledRule, BaseMatcher(),
                          'myfunc')

        # numeric variable
        var = 123
        self.assertRaises(AssertionError, CompiledRule, BaseMatcher(),
                          var)

        class A:
            pass

        # random instance
        self.assertRaises(AssertionError, CompiledRule, BaseMatcher(),
                          A())


    def test_fail_on_invalid_follow_value(self):
        callback = lambda: True
        matcher = BaseMatcher()
        # pass bool
        self.failUnless(CompiledRule(matcher, callback, True))
        self.failUnless(CompiledRule(matcher, callback, False))

        # assert with non-bool
        self.assertRaises(AssertionError, CompiledRule, matcher,
                          callback, None)
        self.assertRaises(AssertionError, CompiledRule, matcher,
                          callback, 1)

    def test_validate_default_attributes(self):
        callback = lambda: True
        matcher = BaseMatcher()
        rule = CompiledRule(matcher, callback, True)

        # test attributes
        self.failUnlessEqual(matcher, rule.matcher)
        self.failUnlessEqual(callback, rule.callback)
        self.failUnlessEqual(True, rule.follow)


class RulesTest(unittest.TestCase):
    def test_rules_manager_basic(self):
        spider = BaseSpider('foo')
        response1 = HtmlResponse('http://example.org')
        response2 = HtmlResponse('http://othersite.org')
        rulesman = RulesManager([], spider)

        # should return none
        self.failIf(rulesman.get_rule_from_response(response1))
        self.failIf(rulesman.get_rule_from_response(response2))

        # rules manager with match-all rule
        rulesman = RulesManager([
                Rule(BaseMatcher(), follow=True),
                ], spider)

        # returns CompiledRule
        rule1 = rulesman.get_rule_from_response(response1)
        rule2 = rulesman.get_rule_from_response(response2)

        self.failUnless(isinstance(rule1, CompiledRule))
        self.failUnless(isinstance(rule2, CompiledRule))
        self.assert_(rule1 is rule2)
        self.failUnlessEqual(rule1.callback, None)
        self.failUnlessEqual(rule1.follow, True)

    def test_rules_manager_empty_rule(self):
        spider = BaseSpider('foo')
        response = HtmlResponse('http://example.org')

        rulesman = RulesManager([Rule(follow=True)], spider)

        rule = rulesman.get_rule_from_response(response)
        # default matcher if None: BaseMatcher
        self.failUnless(isinstance(rule.matcher, BaseMatcher))

    def test_rules_manager_default_matcher(self):
        spider = BaseSpider('foo')
        response = HtmlResponse('http://example.org')
        callback = lambda x: None

        rulesman = RulesManager([
            Rule('http://example.org', callback),
                ], spider, default_matcher=UrlMatcher)

        rule = rulesman.get_rule_from_response(response)
        self.failUnless(isinstance(rule.matcher, UrlMatcher))

    def test_rules_manager_matchers(self):
        spider = BaseSpider('foo')
        response1 = HtmlResponse('http://example.org')
        response2 = HtmlResponse('http://othersite.org')

        urlmatcher = UrlMatcher('http://example.org')
        basematcher = BaseMatcher()
        # callback needed for Rule
        callback = lambda x: None

        # test fail matcher resolve
        self.assertRaises(ValueError, RulesManager,
                          [Rule(False, callback)], spider)
        self.assertRaises(ValueError, RulesManager,
                          [Rule(spider, callback)], spider)

        rulesman = RulesManager([
            Rule(urlmatcher, callback),
            Rule(basematcher, callback),
            ], spider)

        # response1 matches example.org
        rule1 = rulesman.get_rule_from_response(response1)
        # response2 is catch by BaseMatcher()
        rule2 = rulesman.get_rule_from_response(response2)

        self.failUnlessEqual(rule1.matcher, urlmatcher)
        self.failUnlessEqual(rule2.matcher, basematcher)

        # reverse order. BaseMatcher should match all
        rulesman = RulesManager([
            Rule(basematcher, callback),
            Rule(urlmatcher, callback),
            ], spider)

        rule1 = rulesman.get_rule_from_response(response1)
        rule2 = rulesman.get_rule_from_response(response2)

        self.failUnlessEqual(rule1.matcher, basematcher)
        self.failUnlessEqual(rule2.matcher, basematcher)
        self.failUnless(rule1 is rule2)

    def test_rules_manager_callbacks(self):
        mycallback = lambda: True

        spider = BaseSpider('foo')
        spider.parse_item = lambda: True

        response1 = HtmlResponse('http://example.org')
        response2 = HtmlResponse('http://othersite.org')

        rulesman = RulesManager([
            Rule('example', mycallback),
            Rule('othersite', 'parse_item'),
                ], spider, default_matcher=UrlRegexMatcher)

        rule1 = rulesman.get_rule_from_response(response1)
        rule2 = rulesman.get_rule_from_response(response2)

        self.failUnlessEqual(rule1.callback, mycallback)
        self.failUnlessEqual(rule2.callback, spider.parse_item)

        # fail unknown callback
        self.assertRaises(AttributeError, RulesManager, [
                            Rule(BaseMatcher(), 'mycallback')
                            ], spider)
        # fail not callable
        spider.not_callable = True
        self.assertRaises(AttributeError, RulesManager, [
                            Rule(BaseMatcher(), 'not_callable')
                            ], spider)


    def test_rules_manager_callback_with_arguments(self):
        spider = BaseSpider('foo')
        response = HtmlResponse('http://example.org')

        kwargs = {'a': 1}
        
        def myfunc(**mykwargs):
            return mykwargs
        
        # verify return validation
        self.failUnlessEquals(kwargs, myfunc(**kwargs))

        # test callback w/o arguments
        rulesman = RulesManager([
            Rule(BaseMatcher(), myfunc),
            ], spider)
        rule = rulesman.get_rule_from_response(response)

        # without arguments should return same callback
        self.failUnlessEqual(rule.callback, myfunc)

        # test callback w/ arguments
        rulesman = RulesManager([
            Rule(BaseMatcher(), myfunc, **kwargs),
            ], spider)
        rule = rulesman.get_rule_from_response(response)

        # with argument should return partial applied callback
        self.failUnless(isinstance(rule.callback, partial))
        self.failUnlessEquals(kwargs, rule.callback())


