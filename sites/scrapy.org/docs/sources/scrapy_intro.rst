Scrapy Intro
============

Scrapy is a framework designed for retrieving information from websites.
The basic idea of scrapy is to be a bot that goes through websites, getting pages, extracting links and items (which can be any kind of information).
The framework is formed by components that take care of different activities.

These components are *basically*:

* *Core*
* *Spiders*
* *Items*
* *Selectors*
* *Adaptors*


Core
----
Scrapy's core is the most important component (obviously) and the one in charge of getting/receiving information, and delivering it to your spiders (among many other things).
However, we won't talk about the core here, because it doesn't really concern anyone who wants to write spiders, so we'll move on.

Spiders
-------
We'll start off by the spiders because they're the ones that actually use the other components, and they are used themselves by scrapy's core, so they must be the first for you to know about.
Spiders are little programs, let's say, whose purpose is to scrape information from html pages or other data sources. Having said that, it's obvious that their process is something like:
1) Request for information and receive it.
2) Find what you were looking for in the response you got.
3) Adapt it (or not).
4) Store it.

Of course, you won't have to deal with sending requests and receiving responses yourself. Scrapy will do that job for you, so that you can concentrate in the one thing
that probably brought you here: the information.
In order to tell Scrapy how do you want to handle your information, you must define a Spider. This is done by making a class that heredates from BaseSpider.
BaseSpider is a really basic class (as its name suggests), so it doesn't bring you much functionality for scraping HTML pages (since they require you to follow links, and
differentiate many layouts), but it may be useful in case you're doing something totally different, or in case you want to write your own way of crawling.
In other words, BaseSpider is the most simple spider.
It has only these attributes:
* domain_name: which indicates the domain of the website you'd like to scrape in a string.
* start_urls: a list containing the urls you'd like to set as your enter point to the website.
* download_delay: an (optional) delay in seconds to wait before sending each request.

And these two methods:
* init_domain: it's called as soon as the spider is loaded, and it could be useful for initializing stuff.
* parse: this is the most important part of the spider, and it's where any response arrives.

So now you should figure out how spiders work, but just to make it sure, I'll show you an example:::

    from scrapy import log # This module is very useful for printing debug information
    from scrapy.spider import BaseSpider

    class MySpider(BaseSpider):
        domain_name = 'http://www.mywebsite.com'
        start_urls = [
            'http://www.mywebsite.com/1.html',
            'http://www.mywebsite.com/2.html',
            'http://www.mywebsite.com/3.html',
        ]

        def parse(self, response):
            log.msg('Hey! A response from %s has just arrived!' % response.url)
            return []

One **VERY** important thing that I didn't mention before, is the fact that the *parse* method must **always** return a list. Always!
This list may contain either Requests and/or Items (we'll talk about them right now, don't worry).

Now, anybody can fetch web pages -you'll think-, and it's true, you won't get too far by just dealing with that.
And that's when the selectors appear...

Selectors
---------
Selectors are *the* way you have to extract information from documents. They retrieve information from the response's body, given an XPath, or a Regular Expression that you provide.
Currently there are two kinds of selectors, HtmlXPathSelectors, and XmlXPathSelectors. Both work in the same way; they are first instanciated with a response, for example:::

    hxs = HtmlXPathSelector(response)


Now, before going on with selectors, I must tell you about a pretty cool feature that Scrapy has, and which you'll surely find very useful whenever you're writing spiders.
This feature is the Scrapy shell, and you can use it by calling your project manager with the 'shell' argument; something like:::

    [user@host ~/myproject]$ ./scrapy-manager.py shell

Notice that you'll have to install IPython in order to use this feature, but believe me that it worths it; the shell is **very** useful.
With the shell you can simulate parsing a webpage, either by calling "scrapy-manager shell" with an url as an additional parameter, or by using the shell's 'get' command,
which tries to retreive the given url, and fills in the 'response' variable with the result.


Ok, so now let's use the shell to show you a bit how do selectors work.
We'll use an example page located in Scrapy's site (http://docs.scrapy.org/examples/sample1.htm), whose markup is:::

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

First, we open the shell:::

    [user@host ~/myproject]$ ./scrapy-manager.py shell 'http://docs.scrapy.org/examples/sample1.html'

Then, after the shell loads, you'll have some already-made objects for you to play with.
Two of them, hxs and xxs, are selectors.

You could instanciate your own by doing:::

    from scrapy.xpath.selector import HtmlXPathSelector, XmlXPathSelector
    my_html_selector = HtmlXPathSelector(r)
    my_xml_selector = XmlXPathSelector(r)

Where 'r' is the object that scrapy already created for you containing the given url's response.

But anyway, we'll stick to the selectors scrapy already created for us, and more specifically, the HtmlXPathSelector (since we're working with an html document right now)
So let's try some expressions:::

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

You may also have noticed that I've used another method up there; the re() method.
This one is very useful when the data extracted by XPath is not enough and you *have to* (remember to not abuse of regexp) make an extra parsing of the information you've got.
In this cases, you just apply the re() method over any XPathSelector/XPathSelectorList you have with a regexp compile pattern as the only argument, or a string with the pattern to be
compiled.
Remember that the re() method *always* returns a list, which means that you can't go back to a node from the result of a re() call (which is actually pretty obvious).

