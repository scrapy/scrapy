import re
from scrapy import log
from scrapy.http import Request
from scrapy.exceptions import IgnoreRequest
from scrapy.utils.httpobj import urlparse_cached
from scrapy.contrib.downloadermiddleware.redirect import RedirectMiddleware


class RedirectOffsiteMiddleware(RedirectMiddleware):

    def process_response(self, request, response, spider):
        redirected = super(RedirectOffsiteMiddleware, self).process_response(request, response, spider)
        return self.offsite_filtered(redirected, spider)

    def offsite_filtered(self, redirected, spider):

        allowed_domains = getattr(spider, 'allowed_domains', None)

        if not allowed_domains:
            return redirected

        if isinstance(redirected, Request):
            regex = r'^(.*\.)?(%s)$' % '|'.join(re.escape(d) for d in allowed_domains)
            host_regex = re.compile(regex)
            host = urlparse_cached(redirected).hostname or ''
            should_follow = bool(host_regex.search(host))

            if not any((redirected.dont_filter, should_follow) ):
                domain = urlparse_cached(redirected).hostname
                log.msg(format="Filtered offsite request to %(domain)r: %(request)s",
                        level=log.DEBUG, spider=spider, domain=domain, request=redirected)
                raise IgnoreRequest()

        return redirected
