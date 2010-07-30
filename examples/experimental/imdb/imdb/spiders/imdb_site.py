from scrapy.http import Request
from scrapy.selector import HtmlXPathSelector
from scrapy.contrib.loader import XPathItemLoader
from scrapy.contrib_exp.crawlspider import CrawlSpider, Rule
from scrapy.contrib_exp.crawlspider.reqext import SgmlRequestExtractor
from scrapy.contrib_exp.crawlspider.reqproc import Canonicalize, \
        FilterDupes, FilterUrl
from scrapy.utils.url import urljoin_rfc

from imdb.items import ImdbItem, Field

from itertools import chain, imap, izip

class UsaOpeningWeekMovie(ImdbItem):
    pass

class UsaTopWeekMovie(ImdbItem):
    pass

class Top250Movie(ImdbItem):
    rank = Field()
    rating = Field()
    year = Field()
    votes = Field()

class MovieItem(ImdbItem):
    release_date = Field()
    tagline = Field()


class ImdbSiteSpider(CrawlSpider):
    name = 'imdb.com'
    allowed_domains = ['imdb.com']
    start_urls = ['http://www.imdb.com/']

    # extract requests using this classes from urls matching 'follow' flag
    request_extractors = [
        SgmlRequestExtractor(tags=['a'], attrs=['href']),
        ]

    # process requests using this classes from urls matching 'follow' flag
    request_processors = [
        Canonicalize(),
        FilterDupes(),
        FilterUrl(deny=r'/tt\d+/$'), # deny movie url as we will dispatch
                                     # manually the movie requests
        ]

    # include domain bit for demo purposes
    rules = (
        # these two rules expects requests from start url
        Rule(r'imdb.com/nowplaying/$', 'parse_now_playing'),
        Rule(r'imdb.com/chart/top$', 'parse_top_250'),
        # this rule will parse requests manually dispatched
        Rule(r'imdb.com/title/tt\d+/$', 'parse_movie_info'),
    )

    def parse_now_playing(self, response):
        """Scrapes USA openings this week and top 10 in week"""
        self.log("Parsing USA Top Week")
        hxs = HtmlXPathSelector(response)

        _urljoin = lambda url: self._urljoin(response, url)

        #
        # openings this week
        #
        openings = hxs.select('//table[@class="movies"]//a[@class="title"]')
        boxoffice = hxs.select('//table[@class="boxoffice movies"]//a[@class="title"]')

        opening_titles = openings.select('text()').extract()
        opening_urls = imap(_urljoin, openings.select('@href').extract())

        box_titles = boxoffice.select('text()').extract()
        box_urls = imap(_urljoin, boxoffice.select('@href').extract())

        # items 
        opening_items = (UsaOpeningWeekMovie(title=title, url=url)
                            for (title, url)
                            in izip(opening_titles, opening_urls))

        box_items = (UsaTopWeekMovie(title=title, url=url) 
                        for (title, url)
                        in izip(box_titles, box_urls))

        # movie requests
        requests = imap(self.make_requests_from_url,
                        chain(opening_urls, box_urls))

        return chain(opening_items, box_items, requests)

    def parse_top_250(self, response):
        """Scrapes movies from top 250 list"""
        self.log("Parsing Top 250")
        hxs = HtmlXPathSelector(response)

        # scrap each row in the table
        rows = hxs.select('//div[@id="main"]/table/tr//a/ancestor::tr')
        for row in rows:
            fields = row.select('td//text()').extract()
            url, = row.select('td//a/@href').extract()
            url = self._urljoin(response, url)

            item = Top250Movie()
            item['title'] = fields[2]
            item['url'] = url
            item['rank'] = fields[0]
            item['rating'] = fields[1]
            item['year'] = fields[3]
            item['votes'] = fields[4]

            # scrapped top250 item
            yield item
            # fetch movie
            yield self.make_requests_from_url(url)

    def parse_movie_info(self, response):
        """Scrapes movie information"""
        self.log("Parsing Movie Info")
        hxs = HtmlXPathSelector(response)
        selector = hxs.select('//div[@class="maindetails"]')

        item = MovieItem()
        # set url
        item['url'] = response.url

        # use item loader for other attributes
        l = XPathItemLoader(item=item, selector=selector)
        l.add_xpath('title', './/h1/text()')
        l.add_xpath('release_date', './/h5[text()="Release Date:"]'
                                    '/following-sibling::div/text()')
        l.add_xpath('tagline', './/h5[text()="Tagline:"]'
                               '/following-sibling::div/text()')

        yield l.load_item()

    def _urljoin(self, response, url):
        """Helper to convert relative urls to absolute"""
        return urljoin_rfc(response.url, url, response.encoding)
