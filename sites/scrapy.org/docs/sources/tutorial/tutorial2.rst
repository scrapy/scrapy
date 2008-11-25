=========
Selectors
=========

In the last section we have learned how to make an spider, that is, the piece of code that actually does something with data directly retrieved from the web. But we want more than just save this data in a file. We want to extract and classify meaningful data for us. So, first we have to *parse* the data contained in the page. We could use for example regular expressions. And indeed, Scrapy has support for them.

But web pages has a particular language structure, a markup language, that can be easily accessed by more suitable means. One way, and the one adopted by Scrapy, is xpath. Lets suppose we have the following html code::

    <html>
    <head><title>Commodities</title></head>
    <body>
    <table>

    <tr>
    <td>Gold</td>
    <td class=price>939.12US$/oz</td>
    </tr>
    <tr>
    <td>Oil</td>
    <td class=price>123.44US$/bbl</td>
    </tr>

    </table>
    </body>
    </html>

We can access to the title content by the xpath "/html/head/title", which, according to xpath specifications, it is evaluated as "<title>Commodities</title>". "/html/head/title/text()" is evaluated as "Commodities".

If you want to access all the root td elements, the xpath expression is "//td", and the result is multivaluated: "<td>Gold</td>", "<td price=class>939.12US$/oz</td>", "<td>Oil</td>", "<td price=class>123.44US$/bbl</td>".

If want to access all the first <td> tags inside its parent tag (in this case, <tr>), the xpath is "//td![1]", and the result is  multivalued "<td>Gold</td>", "<td>Oil</td>".

Also, you can access tags by attributes. For example, "//td[@class='price']" will match "<td class="price">939.12US$/oz</td>" and "<td class="price">123.44US$/bbl</td>".

The value of the xpath "//body" will be the entire content of the body tag, and so on. For an xpath specifications tutorial see http://www.w3schools.com/xpath/default.asp. I strongly recommend to read that tutorial before continue here. Usually we will not being using such simple xpath expressions.

In order to manage with xpaths, Scrapy defines a class, [source:scrapy/trunk/scrapy/xpath/selector.py XPathSelector]. To access the different elements of a html code, you instantiate the class XPathSelector with a response object. XPathSelector comes in two flavors: XmlXPathSelector and HtmlXPathSelector. At this point I will introduce you a very useful tool: the scrapy console, *shell* so i can ilustrate the use of selectors. I strongly recommend to install IPython package to experience scrapy shell in the most convenient way. Save the above html code in a file, i.e. *sample.html* and run::

    $ ./scrapy-ctl.py shell file://sample.html
    Scrapy 0.1.0 - Interactive scraping console

    Enabling Scrapy extensions... done
    Downloading URL...            done
    ------------------------------------------------------------------------------
    Available local variables:
       xxs: <class 'scrapy.xpath.selector.XmlXPathSelector'>
       url: http://www.bloomberg.com/markets/commodities/cfutures.html
       spider: <class 'scrapy.spider.models.BaseSpider'>
       hxs: <class 'scrapy.xpath.selector.HtmlXPathSelector'>
       item: <class 'scrapy.item.models.ScrapedItem'>
       response: <class 'scrapy.http.response.Response'>
    Available commands:
       get <url>: Fetches an url and updates all variables.
       scrapehelp: Prints this help.
    ------------------------------------------------------------------------------
    Python 2.5.2 (r252:60911, Apr 21 2008, 11:12:42) 
    Type "copyright", "credits" or "license" for more information.

    IPython 0.8.1 -- An enhanced Interactive Python.
    ?       -> Introduction to IPython's features.
    %magic  -> Information about IPython's 'magic' % functions.
    help    -> Python's own help system.
    object? -> Details about 'object'. ?object also works, ?? prints more.

    In [1]:

Ipython is an extended python console, and *shell* command adds some useful local variables and methods, sets python path and imports some scrapy libraries. One of the loaded variables is *response* and contains all the data associated with the result of the request action for the given url. If you enter *response.body.to_unicode()* the downloaded data will be printed on screen.

*xxs* and *hxs* are selectors already instantiated with this response as initialization parameter. *xxs* is a selector with xml 'flavor', and hxs is a selector with html 'flavor'. In the present case, we will use *hxs* You can see selectors as objects that represents nodes in the document structure. So, these instantiated selectors are associated to the root node, or entire document.

Selectors has three methods: *x* *re* and *extract*

 - *x* returns a list of selectors, each of them representing the nodes getted in the xpath expression given as parameter.
 - *re* returns a list of results of a regular expression given as parameter.
 - *extract* actually extracts the data contained in the node. Does not receive parameters.

A list of selectors, a XPathSelectorList object, has the same methods, but they are evaluated on each XPathSelector of the list.

Examples:::

    In [2]: hxs.x("/html")
    Out[1]: [<HtmlXPathSelector (html) xpath=/html>]

    In [2]: hxs.x("//td[@class='price']")
    Out[2]: 
    [<HtmlXPathSelector (td) xpath=//td[@class='price']>,
     <HtmlXPathSelector (td) xpath=//td[@class='price']>]

    In [3]: _.extract()
    Out[3]: 
    [u'<td class="price">939.12US$/oz</td>',
     u'<td class="price">123.44US$/bbl</td>']

    In [4]:hxs.re("\d+.\d+US\$")
    Out[4]: [u'939.12US$', u'123.44US$']

    In [5] hxs.x("//td[2]").re("\d+")
    Out[5]: [u'939', u'12', u'123', u'44']

This is a trivial example. But pages retrieved from the web won't be so simple. Lets suppose we are interested in financial data, and want to extract gold, oil and soy prices from Bloomberg Commodities Page http://www.bloomberg.com/markets/commodities/cfutures.html

Lets try:::

    $ ./scrapy-ctl.py shell http://www.bloomberg.com/markets/commodities/cfutures.html

And inside the scrapy console:::

    In [1]: response.body.to_unicode()
    ...

We will get a big text, and data is not easily targeted there. We need three prices, and can search by try and error, or by aproximation, but it is a tedious job. But someone has developed a very practical tool for doing this: [https://addons.mozilla.org/firefox/addon/1843 Firebug], an add-on for Mozilla Firefox. Install it, then open in your Firefox the Bloomberg url given above. Point the mouse over the Gold row, Price column, click right button and select Inspect Element. This new inspect option has been added by Firebug. A tab will open with the page source code, and highlighted, the code corresponding to the Gold Price:

[[Image(firebug.png)]]

(Observe that pointing the mouse over different elements in code tab, the matching rendered region in browser will be highlighted as well.)

So, you could find the gold price by the xpath expression *span[@class='style5']"* If you type in scrapy console *hxs.x("//span[@class='style5']/text()").extract()* you will get a large list of nodes, because multiple instances of this xpath pattern were found, so you could select that corresponding to gold by the expression *hxs.x("//span[@class='style5']/text()").extract()![73]*

Always there are several ways to target the same element. We could find the same gold price, for example, with the expression *hxs.x("//span[contains(text(),'GOLD')]/../following-sibling::td![1]/span/text()").extract()* And this is an interesting approach, because we could do:::

    In [2]: def get_commodity_price(text):
      ....:      return hxs.x("//span[contains(text(),'%s')]/../following-sibling::td[1]/span/text()" % text).extract()[0]
      ....:

and then,::

    In [3]: get_commodity_price('GOLD')
    Out[3]: u'916.500'

    In [4]: get_commodity_price('WTI CRUDE')
    Out[4]: u'121.590'

    In [5]: get_commodity_price('SOYBEAN FUTURE')
    Out[5]: u'1390.750'

And so on.

So, we can add the following spider to our project:::

    from scrapy.spider import BaseSpider
    from scrapy.xpath import HtmlXPathSelector

    class MySpider(BaseSpider):
        
        domain_name = "bloomberg.com"

        start_urls = ["http://www.bloomberg.com/markets/commodities/cfutures.html"]
        
        def parse(self, response):
            
            hxs = HtmlXPathSelector(response)
            def get_commodity_price(text):
                return hxs.x("//span[contains(text(),'%s')]/../following-sibling::td[1]/span/text()" % text).extract()[0]

            print "Gold Futures NY: %sUS$/oz" % get_commodity_price("GOLD")
            print "Oil WTI Futures: %sUS$/bbl" % get_commodity_price("WTI CRUDE")
            print "Soybean: %sUS$/bu" % get_commodity_price("SOYBEAN FUTURE")
            
            return []

    CRAWLER = MySpider()

Save it as *spiders/bloomberg.py* for example, and enable it adding "bloomberg.com" to *conf/enabled_spiders.list* Actually the name given to the module that contains the spider does not matter. Scrapy will find the correct spider looking for its *domain_name* attribute.

Do a crawl (*scrapy-ctl.py crawl* and both spiders will be ran. We will get printed in part of the log output something like this:::

    2008/07/30 12:40 -0200 [HTTPPageGetter,client] Gold Futures NY: 905.400US$/oz
    2008/07/30 12:40 -0200 [HTTPPageGetter,client] Oil WTI Futures: 121.210US$/bbl
    2008/07/30 12:40 -0200 [HTTPPageGetter,client] Soybean: 1390.750US$/bu

If you want to crawl only one domain among all availables, you just add the domain name to the command line arguments:::

    ./scrapy-ctl.py crawl bloomberg.com
