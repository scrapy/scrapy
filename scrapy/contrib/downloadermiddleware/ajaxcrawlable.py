# -*- coding: utf-8 -*-
from __future__ import absolute_import
import re
from scrapy import log
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse
from scrapy.utils.response import _noscript_re, _script_re
from w3lib import html

class AjaxCrawlableMiddleware(object):
    """
    Handle 'AJAX crawlable' pages marked as crawlable via meta tag.
    For more info see https://developers.google.com/webmasters/ajax-crawling/docs/getting-started.
    """

    # XXX: Google parses at least first 100k bytes; scrapy's redirect
    # middleware parses first 4k. 4k turns out to be insufficient
    # for this middleware, and parsing 100k could be slow.
    _lookup_bytes = 32768

    enabled_setting = 'AJAXCRAWLABLE_ENABLED'

    def __init__(self, settings):
        if not settings.getbool(self.enabled_setting):
            raise NotConfigured

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_response(self, request, response, spider):

        if not isinstance(response, HtmlResponse) or response.status != 200:
            return response

        if request.method != 'GET':
            # other HTTP methods are either not safe or don't have a body
            return response

        if 'ajax_crawlable' in request.meta:  # prevent loops
            return response

        if not self._has_ajax_crawlable_variant(response):
            return response

        # scrapy already handles #! links properly
        ajax_crawlable = request.replace(url=request.url+'#!')
        log.msg(format="Downloading AJAX crawlable %(ajax_crawlable)s instead of %(request)s",
                level=log.DEBUG, spider=spider, ajax_crawlable=ajax_crawlable,
                request=request)

        ajax_crawlable.meta['ajax_crawlable'] = True
        return ajax_crawlable

    def _has_ajax_crawlable_variant(self, response):
        """
        Return True if a page without hash fragment could be "AJAX crawlable"
        according to https://developers.google.com/webmasters/ajax-crawling/docs/getting-started.
        """
        body = response.body_as_unicode()[:self._lookup_bytes]
        return _has_ajaxcrawlable_meta(body)


# XXX: move it to w3lib?
_ajax_crawlable_re = re.compile(ur'<meta\s+name=["\']fragment["\']\s+content=["\']!["\']/?>')
def _has_ajaxcrawlable_meta(text):
    """
    >>> _has_ajaxcrawlable_meta('<html><head><meta name="fragment"  content="!"/></head><body></body></html>')
    True
    >>> _has_ajaxcrawlable_meta("<html><head><meta name='fragment' content='!'></head></html>")
    True
    >>> _has_ajaxcrawlable_meta('<html><head><!--<meta name="fragment"  content="!"/>--></head><body></body></html>')
    False
    >>> _has_ajaxcrawlable_meta('<html></html>')
    False
    """
    text = _script_re.sub(u'', text)
    text = _noscript_re.sub(u'', text)
    text = html.remove_comments(html.remove_entities(text))
    return _ajax_crawlable_re.search(text) is not None
