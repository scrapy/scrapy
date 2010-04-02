"""Crawler Rules"""
from scrapy.http import Request
from scrapy.http import Response

from functools import partial
from itertools import ifilter

from .matchers import BaseMatcher
# default strint-to-matcher class
from .matchers import UrlRegexMatcher

class CompiledRule(object):
    """Compiled version of Rule"""
    def __init__(self, matcher, callback=None, follow=False):
        """Initialize attributes checking type"""
        assert isinstance(matcher, BaseMatcher)
        assert callback is None or callable(callback)
        assert isinstance(follow, bool)

        self.matcher = matcher
        self.callback = callback
        self.follow = follow


class Rule(object):
    """Crawler Rule"""
    def __init__(self, matcher=None, callback=None, follow=False, **kwargs):
        """Store attributes"""
        self.matcher = matcher
        self.callback = callback
        self.cb_kwargs = kwargs if kwargs else {}
        self.follow = True if follow else False

        if self.callback is None and self.follow is False:
            raise ValueError("Rule must either have a callback or "
                             "follow=True: %r" % self)

    def __repr__(self):
        return "Rule(matcher=%r, callback=%r, follow=%r, **%r)" \
                % (self.matcher, self.callback, self.follow, self.cb_kwargs)


class RulesManager(object):
    """Rules Manager"""
    def __init__(self, rules, spider, default_matcher=UrlRegexMatcher):
        """Initialize rules using spider and default matcher"""
        self._rules = tuple()

        # compile absolute/relative-to-spider callbacks"""
        for rule in rules:
            # prepare matcher
            if rule.matcher is None:
                # instance BaseMatcher by default
                matcher = BaseMatcher()
            elif isinstance(rule.matcher, BaseMatcher):
                matcher = rule.matcher
            else:
                # matcher not BaseMatcher, check for string
                if isinstance(rule.matcher, basestring):
                    # instance default matcher
                    matcher = default_matcher(rule.matcher)
                else:
                    raise ValueError('Not valid matcher given %r in %r' \
                                    % (rule.matcher, rule))

            # prepare callback
            if callable(rule.callback):
                callback = rule.callback
            elif not rule.callback is None:
                # callback from spider
                callback = getattr(spider, rule.callback)

                if not callable(callback):
                    raise AttributeError('Invalid callback %r can not be resolved' \
                                            % callback)
            else:
                callback = None

            if rule.cb_kwargs:
                # build partial callback
                callback = partial(callback, **rule.cb_kwargs)

            # append compiled rule to rules list
            crule = CompiledRule(matcher, callback, follow=rule.follow)
            self._rules += (crule, )

    def get_rule_from_request(self, request):
        """Returns first rule that matches given Request"""
        _matches = lambda r: r.matcher.matches_request(request)
        for rule in ifilter(_matches, self._rules):
            # return first match of iterator
            return rule
        
    def get_rule_from_response(self, response):
        """Returns first rule that matches given Response"""
        _matches = lambda r: r.matcher.matches_response(response)
        for rule in ifilter(_matches, self._rules):
            # return first match of iterator
            return rule
 
