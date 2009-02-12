.. _intro-tutorial4:

=================
Finishing the job
=================

Well, we've got our project, our spider, and our scraped items.
What to do next?

It actually depends on what you want to do with the scraped data.  In this
case, we'll imagine that we want to save this data for storing it in a db
later, or just to keep it there.

To make it simple, we'll export the scraped items to a CSV file by making use
of a useful function that Scrapy brings: *items_to_csv*.  This simple function
takes a file descriptor/filename, and a list of items, and writes their
attributes to that file, in CSV format.

.. highlight:: python

Let's see how would our spider end up looking like after applying this change::

    # -*- coding: utf8 -*-
    from scrapy.xpath import HtmlXPathSelector
    from google.items import GoogleItem
    from scrapy.contrib_exp import adaptors
    from scrapy.contrib.spiders import CrawlSpider, Rule
    from scrapy.link.extractors import RegexLinkExtractor
    from scrapy.utils.misc import items_to_csv

    class GoogleDirectorySpider(CrawlSpider):
        domain_name = 'google.com'
        start_urls = ['http://www.google.com/dirhp']

        rules = (
            Rule(RegexLinkExtractor(allow=('google.com/[A-Z][a-zA-Z_/]+$', ), ),
                'parse_category',
                follow=True,
            ),
        )
        csv_file = open('scraped_items.csv', 'ab+')

        def parse_category(self, response):
            # The selector we're going to use in order to extract data from the page
            hxs = HtmlXPathSelector(response)

            # The path to website links in directory page
            links = hxs.x('//td[descendant::a[contains(@href, "#pagerank")]]/following-sibling::td/font')

            # The list of functions to apply to an attribute before assigning its value
            adaptor_pipe = [adaptors.extract, adaptors.Delist(''), adaptors.strip]
            adaptor_map = {
                    'name': adaptor_pipe,
                    'url': adaptor_pipe,
                    'description': adaptor_pipe,
                    }

            for link in links:
                item = GoogleItem()
                item.set_adaptors(adaptor_map)

                item.attribute('name', link.x('a/text()'))
                item.attribute('url', link.x('a/@href'))
                item.attribute('description', link.x('font[2]/text()'))
                items_to_csv(self.csv_file, [item])
                yield item

    SPIDER = GoogleDirectorySpider()


With this code, our spider will crawl over Google's directory, and save each
link's name, description, and url to a file called 'scraped_items.csv'::

    ./scrapy-ctl.py crawl google.com

This is the end of the tutorial. If you'd like to know more about Scrapy and its use, please read the rest of the documentation.
