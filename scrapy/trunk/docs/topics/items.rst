.. _topics-items:

================
Items & Adaptors
================

| In Scrapy, items are the placeholder to use for the scraped data.
  They are represented by a ScrapedItem object, or any descendant class instance, and store the information in class attributes.

These attributes are set by using the item's ``attribute`` method, for example::

    person = ScrapedItem()
    person.attribute('name', 'John')
    person.attribute('age', 35)

Now, normally when we're scraping an HTML file, or almost any kind of file, information doesn't come to us exactly as we need it. We usually
have to make some adaptations here and there; and that's when the adaptors enter the game.

Adaptors
--------

| Adaptors are basically functions that receive one value (advanced adaptors may receive more, but we'll see that later), modify it, and return
  a new value.
| In order to adapt our scraped data we can use an adaptor pipeline for each of the item's attributes.
| Adaptor pipelines are nothing else but a list of adaptors which will be iterated, calling each adaptor and passing the values from one to each other.

| The most common example use of adaptors appears when parsing HTML pages. To do this, we normally use XPathSelectors which need to be extracted some way.
| You could extract them yourself, as well as doing any kind of adaptation before assigning, but the idea of adaptor pipelines is to simplify this task, and the spider's code.

So let's imagine that you want to scrape some information from a page as follows::

    <table id='products_info'>
      <tr>
        <td>Manufacturer/Name</td>
        <td>Weight/Unit</td>
        <td>Price</td>
      </tr>
      <tr>
        <td id='product_name>John &amp; Bill's farm - Bananas</td>
        <td id='product_weight'>1000 gr.</td>
        <td id='product_price'>$ 25</td>
      </tr>
    </table>

You can test yourself with this page, since it actually exists here -> [URL]
Open a Scrapy shell by doing::

    ./scrapy-ctl.py shell [URL]

And then let's try to create the item ourselves. Something like::

    >> from scrapy.item import ScrapedItem
    >> item = ScrapedItem()
    >> item.attribute('manufacturer', hxs.x('//td[@id="product_name"]/text()'))
    >> item.manufacturer
    << ['John &amp; Bill's farm - Bananas']

| Okay, what we did here was creating an item, and setting its 'manufacturer' attribute by using the selector that Scrapy already created for us when the response was downloaded.
| As you can see, we didn't apply the extract method to the selector, but the data got extracted anyway. This is because Scrapy uses scrapy.contrib.adaptors.extract as the default
  adaptor for every attribute, which tries to extract any selector given, or otherwise returns a list containing the received data.

Anyway, that scraped data needs a bit more processing, what about this?::

    >> item = ScrapedItem()
    >> item.add_adaptor('manufacturer', adaptors.Unquote())
    >> item.attribute('manufacturer', hxs.x('//td[@id="product_name"]/text()').re(r'^(.*?) -'))
    >> item.manufacturer
    << ['John & Bill's farm']

| Well, looks much cooler now :)

Let's now try to make a spider to scrape this page::

    from decimal import Decimal
    from scrapy.item import ScrapedItem
    from scrapy.contrib import adaptors
    from scrapy.contrib.spiders import CrawlSpider, Rule
    from scrapy.xpath.selector import HtmlXPathSelector
    from scrapy.link.extractors import RegexLinkExtractor

    class MySpider(CrawlSpider):
        domain_name = 'example.com'
        start_urls = ['http://example.com/items']

        rules = (
            Rule(RegexLinkExtractor(allow=(r'item\d+\.html', )), 'parse_item'),
        )

        def parse_item(self, response):
            item = ScrapedItem()
            item.add_adaptor('manufacturer', adaptors.Unquote())
            item.add_adaptor('price', adaptors.Delist())
            item.add_adaptor('price', Decimal)

            item.attribute('manufacturer', hxs.x('//td[@id="product_name"]/text()').re(r'^(.*?) -'))
            item.attribute('name', hxs.x('//td[@id="product_name"]/text()').re(r'- (.*)$'))
            item.attribute('weight', hxs.x('//td[@id="product_weight"]/text()'))
            item.attribute('price', hxs.x('//td[@id="product_price"]/text()').re(r'$\s*(\d+)'))

            return [item]

    SPIDER = MySpider()


| Basically this spider looks for the product name in the page, splits it in two by using regular expressions and gets the manufacturer
  and product name.
| The manufacturer name may contain entities, as we could see, so we added the ``Unquote`` adaptor to its pipeline. In a real life case, you should probably
  add it to the name attribute too, but it doesn't matter here.
| In order to parse the price, we added two adaptors: Delist, an adaptor that takes care of joining the list returned by the extractor, and Decimal, a class
  from Python's decimal module, whose constructor receives a string and returns a Decimal object.

Scraping the sample page with this code would give us an item similar to::

    ScrapedItem(name='Bananas', manufacturer='John & Bill's farm', weight='1000 gr.', price=Decimal('25'))

There could be more parsing done here through adaptors, like parsing the weight according to its unit, and more; but i'll let you practice on your own.

