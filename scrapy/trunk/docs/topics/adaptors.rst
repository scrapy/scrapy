.. _topics-adaptors:

========
Adaptors
========

Quick overview
==============

| Adaptors are basically functions that receive one value (advanced adaptors may receive more, but we'll see that later), modify it, and return
  a new value.
| In order to adapt our scraped data we can use an adaptor pipeline for each of the item's attributes.
| Adaptor pipelines are nothing else but a list of adaptors which will be iterated, calling each adaptor and passing the values from one to each other.

Example use
===========

| The most common example use of adaptors appears when parsing HTML pages. To do this, we normally use XPathSelectors to retrieve data, which need to be extracted some
  way, and in most cases, filtered some way.
| You could extract them yourself, as well as doing any kind of adaptation before assigning, but the idea of adaptor pipelines is to simplify this task, and the spider's code.

Let's imagine, for example, that you want to scrape information from pages as the following:

.. literalinclude:: ../_static/items_adaptors-sample1.html
   :language: html

| In this case, you'd have to scrape some products information, like their manufacturer, name, and price.
| We'll put this information inside ScrapedItems and attach them some adaptors to process our data better.
| You can test yourself with this page, since it actually exists `here <../_static/items_adaptors-sample1.html>`_

.. highlight:: sh

Open it in a Scrapy shell by doing::

    ./scrapy-ctl.py shell 'http://doc.scrapy.org/_static/items_adaptors-sample1.html'

.. highlight:: python

And then let's try to find the products and scrape an item manually. Something like::

    >>> product_rows = hxs.x('//tr[child::td[@class="prod_attrib"]]')
    >>> product_rows
    [<HtmlXPathSelector (tr) xpath=//tr[child::td[@class="prod_attrib"]]>,
     <HtmlXPathSelector (tr) xpath=//tr[child::td[@class="prod_attrib"]]>]

    # Now we'll play trying to see how we scrape the first product
    >>> from scrapy.item import ScrapedItem
    >>> item = ScrapedItem()
    >>> item.attribute('manufacturer', product_rows[0].x('td[@class="prod_attrib"][1]/text()'))
    >>> item.manufacturer
    [<HtmlXPathSelector (text) xpath=td[@class="prod_attrib"][1]/text()>]

| Okay, what we did here was creating an item, and setting its 'manufacturer' attribute by using the selectors we already had for each product row.
| As you can see, we didn't apply the extract method to the selector, so the data stored in the product was exactly the same that our selector's call to the ``x`` method
  returns; another selector.
  We could extract the information before setting it, but we'll use adaptors instead:

    >>> from scrapy.contrib import adaptors
    >>> item = ScrapedItem()
    >>> item.add_adaptor('manufacturer', adaptors.extract)
    >>> item.attribute('manufacturer', product_rows[0].x('td[@class="prod_attrib"][1]/text()'))
    >>> item.manufacturer
    [u"Bill &amp; Ted's Farm"]

| Better now, right? At least we have some readable data :)
| Although we'd probably want to remove those entities, and to store the information as a string...

    >>> item = ScrapedItem()
    >>> item.set_attrib_adaptors('manufacturer', [
        adaptors.extract,
        adaptors.Unquote(),
        adaptors.Delist() ])
    >>> item.attribute('manufacturer', product_rows[0].x('td[@class="prod_attrib"][1]/text()'))
    >>> item.manufacturer
    u"Bill & Ted's Farm"

| Cool, now that looks like something that can be stored correctly.
| However, we must look at the rest of the attributes too.
| At first sight, it looks like at least the name and the description could use the same adaptors as the manufacturer, since they're all a simple text.

The weight and the price could get a better parsing though; at least to convert them to real decimals. Let's experiment a bit more::

    >>> from decimal import Decimal # We'll use Decimal objects for storing the price and weight

    # We'll also use the same item, since in this case we'll be working with a different attribute
    >>> item.set_attrib_adaptors('price', [ adaptors.Delist(), Decimal ])
    >>> item.attribute('price', product_rows[0].x('td[@class="prod_attrib"][5]/text()').re('(\d+)'))
    >>> item.price
    Decimal('300')

| In this case it wasn't necessary to use the extract adaptor, because applying the ``re`` method over a selector already extracts the resulting content.
| Now, the price was quite easy, but the weight is a bit tricky, for the simple fact that it has more than one weighing unit. In this case, we'll have
  to write our own little adaptor that takes care of parsing a string and returning a Decimal according to its unit.
| Something like this could work, although it's very primitive:

    >>>  def parse_weight(string):
             '''This adaptor receives a string and tries to parse it
             as weight, converting it to grams and returning a Decimal object'''
             conversions = {
                 'kg': Decimal('0.001'),
                 'gr': Decimal('1'),
                 'mg': Decimal('1000'),
             }
             quantity = re.search('(\d+)', string)
             if not quantity:
                 return Decimal('0')
             quantity = Decimal(quantity.group(1))
             for unit in conversions:
                 if unit in string:
                     quantity = quantity / conversions[unit]
                     break
             return quantity

    >>> parse_weight('4kg')
    Decimal('4000')
    >>> parse_weight('200 gr.')
    Decimal('200')
    >>> parse_weight('100 mg')
    Decimal('0.1')

    >>> item.set_attrib_adaptors('weight', [
        adaptors.extract,
        adaptors.Delist(),
        parse_weight ])
    >>> item.attribute('weight', product_rows[0].x('td[@class="prod_attrib"][4]/text()').re('(\d+)'))
    >>> item.weight
    Decimal('2000')

Ok, done! Let's now sum this up into a spider::

    from decimal import Decimal
    from scrapy.item import ScrapedItem
    from scrapy.contrib import adaptors
    from scrapy.contrib.spiders import CrawlSpider, Rule
    from scrapy.xpath.selector import HtmlXPathSelector
    from scrapy.link.extractors import RegexLinkExtractor

    def parse_weight(string):
        conversions = {
            'kg': Decimal('0.001'),
            'gr': Decimal('1'),
            'mg': Decimal('1000'),
        }

        quantity = re.search('(\d+)', string)
        if not quantity:
            return Decimal('0')
        quantity = Decimal(quantity.group(1))

        for unit in conversions:
            if unit in string:
                quantity = quantity / conversions[unit]
                break
        return quantity

    class MySpider(CrawlSpider):
        domain_name = 'scrapy.org'
        start_urls = ['http://doc.scrapy.org/_static/items_adaptors-sample1.html']

        rules = (
            Rule(RegexLinkExtractor(allow=(r'sample\d+\.html', )), 'parse_page'),
        )

        adaptors = {
            'manufacturer': [ adaptors.extract, adaptors.Unquote(), adaptors.Delist() ],
            'name': [ adaptors.extract, adaptors.Unquote(), adaptors.Delist() ],
            'description': [ adaptors.extract, adaptors.Unquote(), adaptors.Delist() ],
            'weight': [ adaptors.extract, adaptors.Delist(), parse_weight ],
            'price': [ adaptors.Delist(), Decimal ]
        }

        def parse_page(self, response):
            rows = hxs.x('//tr[child::td[@class="prod_attrib"]]')
            for product in rows:
                item = ScrapedItem()
                item.set_adaptors(self.adaptors)

                item.attribute('manufacturer', product.x('td[@class="prod_attrib"][1]/text()'))
                item.attribute('name', product.x('td[@class="prod_attrib"][2]/text()'))
                item.attribute('description', product.x('td[@class="prod_attrib"][3]/text()'))
                item.attribute('weight', product.x('td[@class="prod_attrib"][4]/text()'))
                item.attribute('price', product.x('td[@class="prod_attrib"][5]/text()').re('(\d+)'))

            return [item]

    SPIDER = MySpider()


| Basically this spider looks for the product rows in the page, creates an item for each of them, attaches them some adaptors, and fills their attributes in.

Scraping the sample page with this code would give us these items::

    ScrapedItem({u"name": u"Bananas", u"manufacturer": u"Bill & Ted's farm", u"description": "Delicious fruit", u"weight": Decimal("2000"), u"price": Decimal("300")})
    ScrapedItem({u"name": u"Apple pie", u"manufacturer": u"Grandma's", u"description": "Grandma's best dish", u"weight": Decimal("250"), u"price": Decimal("200")})

There could be more parsing done here through adaptors, like parsing different price currencies, or more advanced weight parsing (this one was very, very, simple and buggy).
Nevertheless, I hope that this was useful as an example use of adaptors.
