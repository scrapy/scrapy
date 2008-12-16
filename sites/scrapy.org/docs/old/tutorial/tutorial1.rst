================
Our first spider
================

Lets code our first spider. But before, lets check two important asociated settings in *conf/scrapy_settings.py* file::

    SPIDER_MODULES = ['myproject.spiders']
    ENABLED_SPIDERS_FILE = '%s/conf/enabled_spiders.list' % myproject.__path__[0]

The first setting, SPIDER_MODULES, is a list that sets the modules that contains the spiders. The second one, ENABLED_SPIDERS_FILE, sets the location of a text file that contains the list of enabled spiders. When you created the project branch, the admin script set both for you. Hence, you will see that with these values, **Scrapy** will search spiders in the module *myproject.spiders* and will read the enabled spiders list from the path *path to myproject>/myproject/conf/enabled_spiders.list* where *<path to myproject>* is the path where the module *myproject* resides on. Of course, you can change this settings as taste. These are just defaults to help you.

Now, finally, the code to our first spider::

    from scrapy.spider import BaseSpider

    class MySpider(BaseSpider):
        
        domain_name = "scrapy.org"

        start_urls = ["http://dev.scrapy.org/wiki/WikiStart", "http://dev.scrapy.org/wiki/Starting"]
        
        def parse(self, response):
            filename = response.url.split("/")[-1]
            open(filename, "w").write(response.body.to_unicode())

            return []
            
    CRAWLER = MySpider()

The first line imports the class [source:scrapy/trunk/scrapy/spider/models.py BaseSpider]. For the purpose of creating a working spider, you must subclass !BaseSpider, and then define the three main, mandatory, attributes:

* *domain_name* identifies the spider. It must be unique, that is, you can't set the same domain name for different spiders.
* *start_urls* is a list of urls where the spider will begin to crawl from. So, the first pages downloaded will be those listed here. The subsequent urls will be generated successively from data contained in the start urls.
* *parse* is the callback method of the spider. This means that each time a page is retrieved, the downloaded data will be passed to this method. In this simple example, the only action is to save the data. But anything can be done here: parse the data, organize it and store in a db or in the filesystem, process it, get new urls to continue the crawling process, etc.

*parse()* method must always return a list. We will see why later.

In the last line, we instantiate our spider class.

So, save this code in a file named myfirst.py inside *myproject/spiders* folder, and create the file *conf/enabled_spiders.list* with the content::

    scrapy.org

to enable our new spider.

Now, go to myproject base folder and run::

    ./scrapy-ctl.py crawl

The **crawl** subcommand runs all the enabled spiders. The output of this command will be something like::

    2008/07/27 19:46 -0200 [-] Log opened.
    2008/07/27 19:46 -0200 [scrapy-bot] INFO: Enabled extensions: TelnetConsole, WebConsole
    2008/07/27 19:46 -0200 [scrapy-bot] INFO: Enabled downloader middlewares: 
    2008/07/27 19:46 -0200 [scrapy-bot] INFO: Enabled spider middlewares: 
    2008/07/27 19:46 -0200 [scrapy-bot] INFO: Enabled item pipelines: 
    2008/07/27 19:46 -0200 [scrapy-bot/scrapy.org] INFO: Domain opened
    2008/07/27 19:46 -0200 [scrapy-bot/scrapy.org] DEBUG: Crawled live <http://dev.scrapy.org/wiki/WikiStart> from <None>
    2008/07/27 19:46 -0200 [scrapy-bot/scrapy.org] DEBUG: Crawled live <http://dev.scrapy.org/wiki/Starting> from <None>
    2008/07/27 19:46 -0200 [scrapy-bot/scrapy.org] INFO: Domain closed (finished)
    2008/07/27 19:46 -0200 [-] Main loop terminated.

Pay attention to the lines labeled [scrapy-bot/scrapy.org], which corresponds to our spider identified by the domain "scrapy.org". You can see a log line for each url defined in *start_urls*. Because these urls are the starting ones, they have no referrers, and this condition is indicated at the end of the log line, where it says *from <None>*.

But more interesting, as our *parse* method instructs, two files have been created: WikiStart and Starting, with the content of both urls.

If you remember the elemental loop scheme of Scrapy described before:

1. Feed the application with an initial set of urls.
2. Create a Request object for each given url.
3. Attach callback functions to each Request, so you define what to do with data once arrives.
4. Feed the Execution Engine with a list of Requests and data.

You will see that the sample spider we made here (and all spiders) actually performes step 1 and 3. But behind the scenes, step 2 and 4 are also carried out. Most spiders will explicitly create Requests. And they don't need to call the engine by themselves. In fact, they will never do that.
