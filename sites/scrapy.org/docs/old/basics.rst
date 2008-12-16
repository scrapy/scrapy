======
Basics
======

Scrapy is built up on `Twisted <http://twistedmatrix.com>`_ , a python platform for the developing of network applications in an asynchronous (non-blocking) approach. This means that, while running in a single thread, a Scrapy application does not block while waiting data arrival from the network. Instead, it continues to process any task that requires CPU attention. Then, when data arrives, a callback function is called with this data as parameter. This is why this kind of code is also called event-driven or callback-based. For more information about this issue see `Asynchronous Programming with Twisted <http://twistedmatrix.com/projects/core/documentation/howto/async.html>`_.

When coding with Scrapy, the elemental scheme loop is: 

1. Feed the application with an initial set of urls.
2. Create a [source:scrapy/trunk/scrapy/http/request.py Request] object for each given url.
3. Attach callback functions to each Request, so you define what to do with data once arrives.
4. Feed the [source:scrapy/trunk/scrapy/core/engine.py Execution Engine] with a list of Requests and data.

Eventually, the callbacks can return data or more Request objects to the Execution Engine, so the crawling process will continue until no more request left.

At this point, it may seem that Scrapy can't do anything that cannot be done easily with Twisted. But the magic of Scrapy resides on that it helps the developer to implement this basic scheme under a very simple and straightforward model and, most important, on all the fully integrated helpers that places at developer disposal in order to perform intensive network crawling and quickly deploy a fully functional application.

These helpers includes

* Parsers/interpreters for most common languages found in the web (xml/html/csv/javascript).
* Network request and response pre and post process pluggable middleware to comply with specific network tasks, such as HTTP authentication, redirection, compression, network caching, network debug info logging, download retrying, cookie management, etc.
* Scraping results post process pluggable middleware.
* Pluggable extensions such as memory debugging, memory usage control and profiling, cpu profiling, controlling web/webservice and telnet consoles, distributed crawling cluster, scraping statistics and lot more.
* Built-in event signaling.
* Spiders quality test tools.
* Lots of useful utilities for many kinds of data processing.

In order to implement all these resources, Scrapy heavily exploits the concept of middleware. Middleware is plugin code organized in a pipeline model, that resides in the execution line between the spiders, the engine and the Web.

So, if you don't want to start from the very begining a serious production crawling/scraping project, Scrapy is for you.

Getting Scrapy and starting a new project 
=========================================

Scrapy is under heavy development, so you will want to download it from his svn repository::

  svn co http://svn.scrapy.org/scrapy

This command will create a folder with the name *scrapy* You can find **scrapy** module under *scrapy/trunk* so in order to import this module, assure you have its absolute path in your PYTHONPATH environment variable.

In order to start a new project, Scrapy gives you a script tool that helps to generate a basic folder structure for the new project, an initial settings file, and a control script.

Do::

  $ scrapy/trunk/scrapy/bin/scrapy-admin.py startproject myproject

You will see that a new folder, *myproject*, in your actual path, was created. Let's continue in the scrapy tutorial.
