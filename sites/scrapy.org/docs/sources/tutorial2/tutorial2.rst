================
Our first spider
================

| Ok, the time to write our first spider has come.
| Make sure you're standing on your project's directory and run:

::

    ./scrapy-ctl genspider dmoz dmoz.org

This should create a file called dmoz.py under the *spiders* directory looking similar to this::

    # -*- coding: utf8 -*-<
    import re
    from scrapy.xpath import HtmlXPathSelector
    from scrapy.item import ScrapedItem
    from scrapy.link.extractors import RegexLinkExtractor
    from scrapy.contrib.spiders import CrawlSpider, Rule

    class DmozSpider(CrawlSpider):
        domain_name = "dmoz.org"
        start_urls = ['http://www.dmoz.org/']

        rules = (
            Rule(RegexLinkExtractor(allow=(r'Items/', ), 'parse_item', follow=True)
        )

        def parse_item(self, response):
            #xs = HtmlXPathSelector(response)
            #i = ScrapedItem()
            #i.attribute('site_id', xs.x("//input[@id="sid"]/@value"))
            #i.attribute('name', xs.x("//div[@id='name']"))
            #i.attribute('description', xs.x("//div[@id='description']"))
            #return [i]

    SPIDER = DmozSpider()

