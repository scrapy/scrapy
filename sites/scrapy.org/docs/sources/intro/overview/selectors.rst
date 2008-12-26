.. _selectors:

Selectors
---------
Selectors are *the* way you have to extract information from documents. They retrieve information from the response's body, given an XPath, or a Regular Expression that you provide.

Currently there are two kinds of selectors, HtmlXPathSelectors, and XmlXPathSelectors. Both work in the same way; they are first instanciated with a response, for example::

    hxs = HtmlXPathSelector(response) # an HTML selector
    xxs = XmlXPathSelector(response) # an XML selector

Now, before going on with selectors, I must tell you about a pretty cool feature that Scrapy has, and which you'll surely find very useful whenever you're writing spiders.

This feature is the Scrapy shell, and you can use it by calling your project manager with the 'shell' argument; something like::

    [user@host ~/myproject]$ ./scrapy-manager.py shell <url>

Notice that you'll have to install IPython in order to use this feature, but believe me that it worths it; the shell is **very** useful.

With the shell you can simulate parsing a webpage, either by calling "scrapy-manager shell" with an url as an additional parameter, or by using the shell's 'get' command, which tries
to retreive the given url, and fills in the 'response' variable with the result.

Ok, so now let's use the shell to show you a bit how do selectors work.
We'll use an example page located in Scrapy's site (http://docs.scrapy.org/examples/sample1.htm), whose markup is::

    <html>
     <head>
      <base href='http://mywebsite.com/' />
      <title>My website</title>
     </head>
     <body>
      <div id='images'>
        <a href='image1.html'>Name: My image 1 <br /><img src='image1_thumb.jpg' /></a>
        <a href='image2.html'>Name: My image 2 <br /><img src='image2_thumb.jpg' /></a>
        <a href='image3.html'>Name: My image 3 <br /><img src='image3_thumb.jpg' /></a>
        <a href='image4.html'>Name: My image 4 <br /><img src='image4_thumb.jpg' /></a>
        <a href='image5.html'>Name: My image 5 <br /><img src='image5_thumb.jpg' /></a>
      </div>
     </body>
    </html>

First, we open the shell::

    [user@host ~/myproject]$ ./scrapy-manager.py shell 'http://docs.scrapy.org/examples/sample1.html'

Then, after the shell loads, you'll have some already-made objects for you to play with. Two of them, hxs and xxs, are selectors.

You could instanciate your own by doing::

    from scrapy.xpath.selector import HtmlXPathSelector, XmlXPathSelector
    my_html_selector = HtmlXPathSelector(r)
    my_xml_selector = XmlXPathSelector(r)

Where 'r' is the object that scrapy already created for you containing the given url's response.

But anyway, we'll stick to the selectors scrapy already created for us, and more specifically, the HtmlXPathSelector (since we're working with an html document right now).

Let's try some expressions::

    # The title
    In [1]: hxs.x('//title/text()')
    Out[1]: [<HtmlXPathSelector (text) xpath=//title/text()>]
    # As you can see, the x method returns an XPathSelectorList, which is actually a list of selectors.
    # To extract their data you must use the extract() method, as follows:
    In [2]: hxs.x('//title/text()').extract()
    Out[2]: [u'My website']

    # The base url
    In [3]: hxs.x('//base/@href').extract()
    Out[3]: [u'http://mywebsite.com/']

    # Image links
    In [4]: hxs.x('//a[contains(@href, "image")]/@href').extract()
    Out[4]:
    [u'image1.html',
     u'image2.html',
     u'image3.html',
     u'image4.html',
     u'image5.html']

    # Image thumbnails
    In [5]: hxs.x('//a[contains(@href, "image")]/img/@src').extract()
    Out[5]:
    [u'image1_thumb.jpg',
     u'image2_thumb.jpg',
     u'image3_thumb.jpg',
     u'image4_thumb.jpg',
     u'image5_thumb.jpg']

    # Image names
    In [6]: hxs.x('//a[contains(@href, "image")]/text()').re(r'Name:\s*(.*)')
    Out[6]:
    [u'My image 1',
     u'My image 2',
     u'My image 3',
     u'My image 4',
     u'My image 5']


Ok, let's explain a bit.
Selector's x() method, is intended to select a node or an attribute from the document, given an XPath expression, as you could see upwards.
You can apply an x() call to any node you have, which means that you can join different calls, for example:::

    In [10]: links = hxs.x('//a[contains(@href, "image")]')

    In [11]: links.extract()
    Out[11]:
    [u'<a href="image1.html">Name: My image 1 <br><img src="image1_thumb.jpg"></a>',
     u'<a href="image2.html">Name: My image 2 <br><img src="image2_thumb.jpg"></a>',
     u'<a href="image3.html">Name: My image 3 <br><img src="image3_thumb.jpg"></a>',
     u'<a href="image4.html">Name: My image 4 <br><img src="image4_thumb.jpg"></a>',
     u'<a href="image5.html">Name: My image 5 <br><img src="image5_thumb.jpg"></a>']

    In [12]: for index, link in enumerate(links):
                print 'Link number %d points to url %s and image %s' % (index, link.x('@href').extract(), link.x('img/@src').extract())

    Link number 0 points to url [u'image1.html'] and image [u'image1_thumb.jpg']
    Link number 1 points to url [u'image2.html'] and image [u'image2_thumb.jpg']
    Link number 2 points to url [u'image3.html'] and image [u'image3_thumb.jpg']
    Link number 3 points to url [u'image4.html'] and image [u'image4_thumb.jpg']
    Link number 4 points to url [u'image5.html'] and image [u'image5_thumb.jpg']

There are some things to keep in mind here:

1. | x() calls always return an XPathSelectorList, which is basically a list of selectors, with the extra ability of applying XPath or Regexp to each of its items and returning a new list.
   | That's why you can concatenate x() calls, because they always return XPathSelectorLists, and you can always reapply that method over them.
2. x() calls are relative to the node your standing on, so selector.x('body/div[@id="mydiv"]') equals selector.x('body').x('div[@id="mydiv"]').
3. The extract() method *always* returns a list, even if it contains only one element. Don't forget that.

| You may also have noticed that I've used another method up there; the re() method.
| This one is very useful when the data extracted by XPath is not enough and you *have to* (remember to not abuse of regexp) make an extra parsing of the information you've got.
| In this cases, you just apply the re() method over any XPathSelector/XPathSelectorList you have with a compiled regexp pattern as the only argument, or a string with the pattern to be compiled.
| Remember that the re() method *always* returns an already extracted list, which means that you can't go back to a node from the result of a re() call (which is actually pretty obvious).

