"""
Simple script to follow links from a start url. The links are followed in no
particular order.

Usage:
count_and_follow_links.py <start_url> <links_to_follow>

Example:
count_and_follow_links.py http://scrapy.org/ 20

For each page visisted, this script will print the page body size and the
number of links found.
"""

import sys
from urlparse import urljoin

from scrapy.crawler import Crawler
from scrapy.selector import HtmlXPathSelector
from scrapy.http import Request, HtmlResponse

links_followed = 0

def parse(response):
    global links_followed
    links_followed += 1
    if links_followed >= links_to_follow:
        crawler.stop()

    # ignore non-HTML responses
    if not isinstance(response, HtmlResponse):
        return

    links = HtmlXPathSelector(response).select('//a/@href').extract()
    abslinks = [urljoin(response.url, l) for l in links]

    print "page %2d/%d: %s" % (links_followed, links_to_follow, response.url)
    print "  size : %d bytes" % len(response.body)
    print "  links: %d" % len(links)
    print

    return [Request(l, callback=parse) for l in abslinks]

if len(sys.argv) != 3:
    print __doc__
    sys.exit(2)

start_url, links_to_follow = sys.argv[1], int(sys.argv[2])
request = Request(start_url, callback=parse)
crawler = Crawler()
crawler.crawl(request)
