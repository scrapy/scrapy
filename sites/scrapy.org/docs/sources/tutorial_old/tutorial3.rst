==================
Items and Adaptors
==================

At this point we have seen how to scrape data from a web page. But the only thing we did was to print it in the screen. Frequently we need to organize, process, or store the data we have retrieved. In order to perform these jobs, Scrapy model includes a data encapsulation class: [source:scrapy/trunk/scrapy/item/models.py ScrapedItem].

A [source:scrapy/trunk/scrapy/item/models.py ScrapedItem] contains attributes with given values, just like any python object. And you use the method *attribute* in order to assign to the item an attribute with a given value and name. Of course, you could do something like::

    index.name = "Gold Future"
    index.value = get_commodity_price("GOLD")

being *index* an instance of a given object class. But *attribute* method is intended to do more than just assign. Very often data from the web contains entities, tags, or comes inside a piece of text, and are always strings. But you may want to remove or not entities and tags depending on attribute name, or extract significative data from a bigger text (i.e. dimensions or prices inside a text), convert data to float, integers, and validate data assigned, or normalize some data features. You could do all this inside the spider code. But in this manner you will repeat lot of code, and even generate data inconsistencies from spider to spider simply because you forget to apply correct data processing according to policies you have pre-established (imagine when working with lots and lots of different spiders and source webpages)

When you use the *attribute* method, the data passes through an adaptation pipeline before finally be assigned. The purpose of this adaptation pipeline is preciselly to apply all the data processing in a user-defined, simple and scalable way, and without having to implement it inside the spiders code each time you add a new one.

Lets continue our bloomberg commodities example. Modify our bloomberg.py file as follows:::

    from scrapy.spider import BaseSpider
    from scrapy.xpath import HtmlXPathSelector

    from scrapy.item import ScrapedItem as FinancyIndex

    class BloombergSpider(BaseSpider):
        
        domain_name = "bloomberg.com"

        start_urls = ["http://www.bloomberg.com/markets/commodities/cfutures.html",
                      "http://www.bloomberg.com/markets/stocks/movers_index_spx.html"]
        
        def parse(self, response):

            hxs = HtmlXPathSelector(response)
            
            def get_commodity_price(text):
                value = hxs.x("//span[contains(text(),'%s')]/../following-sibling::td[1]/span/text()" % text).extract()[0]
                unit = hxs.x("//span[contains(text(),'%s')]/following-sibling::span" % text).re("\((.*)\)")[0]
                return value, unit
            
            def get_index_value():
                return hxs.x("//span[contains(text(),'VALUE')]/../following-sibling::td/text()").extract()[0]

            items = []
            if "cfutures" in response.url:
                for i in [("GOLD", "Gold Futures NY"), ("WTI CRUDE", "Oil WTI Futures"), ("SOYBEAN FUTURE", "Soybean")]:
                    index = FinancyIndex()
                    index.attribute("name", i[1])
                    value, unit = get_commodity_price(i[0])
                    index.attribute("value", value)
                    index.attribute("unit", unit)
                    items.append(index)
            elif "index_spx" in response.url:
                index = FinancyIndex()
                index.attribute("name", "S&P500")
                index.attribute("value", get_index_value())
                index.attribute("unit", "%")
                items.append(index)
            return items

    CRAWLER = BloombergSpider()

Note two important differences with our previous version:

* We have added a second url in our *start_urls* list. This means our spider will visit two webpages. In order to handle this, we have splitted our code in two parts, according to the response url, one that handles commodities page , and other which handles Standard&Poor's index page. We can add any ammount of urls we want to visit in the *start_urls* list. But this is an inefficient approach if we want to scrape lots of pages from a site (it is common to visit hundreds or even thousands of them). Further we will learn crawling techniques with Scrapy in order to generate and follow links in a site, beginning from few starting urls.
* Instead of printing scraped data in the console, we assign it to [source:scrapy/trunk/scrapy/item/models.py ScrapedItem] objects. Each item contains three attributes: name, value and unit (also, we have added code to scrape units). Then, *parse* method returns a list of the scraped items. Remember we said in previous section that *parse* must always return a list.

If we run the scrapy shell with our commodity url as parameter and run *spider.parse(response)* we will get a list of three items:::

    In [1]: spider.parse(response)
    Out[1]: 
    [<scrapy.item.models.ScrapedItem object at 0x8ae602c>,
     <scrapy.item.models.ScrapedItem object at 0x8ae616c>,
     <scrapy.item.models.ScrapedItem object at 0x8ae606c>]

So parse is doing what we expect: it returns three items, one for each index. If we want to see a more detailed output, *scrapy-ctl* proportionates another useful tool: the *parse* subcommand. Try:::

    $ ./scrapy-ctl.py parse http://www.bloomberg.com/markets/commodities/cfutures.html
    2008/09/02 17:40 -0200 [-] Log opened.
    2008/09/02 17:40 -0200 [scrapy-bot] INFO: Enabled extensions: TelnetConsole, WebConsole
    2008/09/02 17:40 -0200 [scrapy-bot] INFO: Enabled downloader middlewares: 
    2008/09/02 17:40 -0200 [scrapy-bot] INFO: Enabled spider middlewares: 
    2008/09/02 17:40 -0200 [scrapy-bot] INFO: Enabled item pipelines: 
    2008/09/02 17:40 -0200 [scrapy-bot/bloomberg.com] INFO: Domain opened
    2008/09/02 17:40 -0200 [scrapy-bot/bloomberg.com] DEBUG: Crawled live <http://www.bloomberg.com/markets/commodities/cfutures.html> from <None>
    2008/09/02 17:40 -0200 [scrapy-bot/bloomberg.com] INFO: Domain closed (finished)
    2008/09/02 17:40 -0200 [-] Main loop terminated.
    # Scraped Items ------------------------------------------------------------
    ScrapedItem({'name': 'Gold Futures NY', 'unit': u'USD/t oz.', 'value': u'812.700'})
    ScrapedItem({'name': 'Oil WTI Futures', 'unit': u'USD/bbl.', 'value': u'110.430'})
    ScrapedItem({'name': 'Soybean', 'unit': u'USd/bu.', 'value': u'1298.500'})

    # Links --------------------------------------------------------------------

    $ 

We get a nice printing of our items, displaying all their attributes. Observe that attribute values are raw data, extracted as is from the page. All are strings, and we could be interested in operate with decimal values; units expressions are not homogeneous (see dollar symbols are USD and USd), and we did not give unicode strings as items name. So, lets construct an adaptor pipeline and create our own item class for this purpose:::

    from decimal import Decimal
    import re

    from scrapy.item.models import ScrapedItem
    from scrapy.item.adaptors import AdaptorPipe

    def extract(value):
        if hasattr(value, 'extract'):
            value = value.extract()
        if isinstance(value, list):
            value = value[0]
        return value

    def to_decimal(value):
        return Decimal(value)

    def to_unicode(value):
        return unicode(value)

    _dollars_re = re.compile("[Uu][Ss][Dd]")
    def normalize_units(value):
        return _dollars_re.sub("U$S", value)

    def clean(value):
        return value.strip()

    def clean_number(value):
        if value.find(".") > value.find(","):
            value = value.replace(",", "")
        elif value.find(",") > value.find("."):
            value = value.replace(".", "")
        value = value.replace(",", ".")
        return value

    pipedict = {
     'name': [extract, to_unicode, clean],
     'unit': [extract, to_unicode, clean, normalize_units],
     'value': [extract, to_unicode, clean, clean_number, to_decimal]
    }

    class FinancyIndex(ScrapedItem):

        adaptors_pipe = AdaptorPipe(pipedict)


Save this as *item.py* and in the bloomberg spider code, replace the line::

    from scrapy.item import ScrapedItem as FinancyIndex

by::

    from financy.item import FinancyIndex

Also, you can remove the *extract()* and *0]* in our helper functions *get_commodity_price* and *get_index_value*::

    def get_commodity_price(text):
        value = hxs.x("//span[contains(text(),'%s')]/../following-sibling::td[1]/span/text()" % text)
        unit = hxs.x("//span[contains(text(),'%s')]/following-sibling::span" % text).re("\((.*)\)")
        return value, unit
    
    def get_index_value():
        return hxs.x("//span[contains(text(),'VALUE')]/../following-sibling::td/text()")v

The extract adaptor will do that for us.

Run *parse* command again:::

    # Scraped Items ------------------------------------------------------------
    FinancyIndex({'name': u'Gold Futures NY', 'unit': u'U$S/t oz.', 'value': Decimal("809.600")})
    FinancyIndex({'name': u'Oil WTI Futures', 'unit': u'U$S/bbl.', 'value': Decimal("110.240")})
    FinancyIndex({'name': u'Soybean', 'unit': u'U$S/bu.', 'value': Decimal("1298.500")})

Very nice, uh? And this adaptor pipeline will be applied for all spiders you add to your project --which is the purpose of the adaptor pipeline--, provided you use the item *attribute* method to assign them.

Adaptors run in the specified order. And you must take care that each adaptor receives from the previous one, what expects to receive. In order to enable an adaptors pipeline, you have to instantiate an [source:scrapy/trunk/scrapy/item/adaptors.py AdaptorPipe] class in your item class (in this example, *financy.item.FinancyIndex*) with a dictionary which maps *attribute name* to a pipeline of adaptation functions, and assign it to the class attribute *adaptors_pipe*.

You can at anytime edit the pipeline by accessing to *pipe* attribute of the !AdaptorPipe instance. For example, you may want to remove or add an adaptor from a spider code for a certain group of attributes. But you must take on account that, because the pipeline is a class attribute, any change will has effect on all.
