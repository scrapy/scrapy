.. _topics-spiders:

=======
Spiders
=======

We'll start off by the spiders because they're the ones that actually use the other components, and they are used themselves by scrapy's core, so they must be the first for you to know about.

Spiders are little programs, let's say, whose purpose is to scrape information from html pages or other data sources. Having said that, it's obvious that their process is something like:

1. Request for information and receive it.
2. Find what you were looking for in the response you got.
3. Adapt it (or not).
4. Store it.

Of course, you won't have to deal with sending requests and receiving responses yourself. Scrapy will do that job for you, so that you can concentrate in the one thing that probably
brought you here: the information.

In order to tell Scrapy how do you want to handle your information, you must define a Spider. This is done by making a class that inherits from BaseSpider.
BaseSpider is a really basic class (as its name suggests), so it doesn't bring you much functionality for scraping HTML pages (since they require you to follow links,
and differentiate many layouts), but it may be useful in case you're doing something totally different, or in case you want to write your own way of crawling.

In other words, BaseSpider is the most simple available spider.

It has only these three attributes:

* domain_name: which indicates in a string the domain of the website you'd like to scrape.
* start_urls: a list containing the URLs you'd like to set as your entry point to the website.
* download_delay: an (optional) delay in seconds to wait before sending each request.

And these two methods:

* init_domain: it's called as soon as the spider is loaded, and it could be useful for initializing stuff.
* parse: this is the most important part of the spider, and it's where any response arrives.

So now you should figure out how spiders work, but just to make it sure, I'll show you an example::

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
This list may contain either Requests and/or Items (we'll talk about them later, don't worry).

Now, anybody can fetch web pages -you'll think-, and it's true, you won't get too far by just dealing with that.
And that's when the selectors make their appeareance...

