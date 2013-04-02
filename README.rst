======
Scrapy
======

.. image:: https://secure.travis-ci.org/scrapy/scrapy.png?branch=master
   :target: http://travis-ci.org/scrapy/scrapy

# About avoid getting banned:


# GoogleCacheMiddleware:

<pre>
      this is a downloadmiddle to avoid getting banned,you can set the 
GOOGLE_CACHE_DOMAINS variable or you can set the user_agent_list 
attribute in your spider to define what domain you will use to visit the 
google cache,it is a list,eg:GOOGLE_CACHE_DOMAINS = ['www.woaidu.org',]
</pre>
# RotateUserAgentMiddleware:
<pre>
      this is also a downloadmiddleware to avoid getting banned,you can 
set the USER_AGENT_LIST in settings,then the middleware will random
 choose one of them as the user-agent,if you don't define it,then it will 
use the default user-aget,it contains chrome,I E,firefox,Mozilla,opera,netscape.
</pre>
# how to use them:
## for GoogleCacheMiddleware:
<pre>
         add "scrapy.contrib.downloadermiddleware.google_cache.GoogleCacheMiddleware":50
 in your DOWNLOADER_MIDDLEWARES,and define GOOGLE_CACHE_DOMAINSin your 
settings,eg: ['www.woaidu.org',]
</pre>
## for RotateUserAgentMiddleware:
<pre>
       add 'scrapy.contrib.downloadermiddleware.useragent.UserAgentMiddleware': None,
'woaidu_crawler.contrib.downloadmiddleware.rotate_useragent.RotateUserAgentMiddleware'
:400, in your DOWNLOADER_MIDDLEWARES.
</pre>


Overview
========

Scrapy is a fast high-level screen scraping and web crawling framework, used to
crawl websites and extract structured data from their pages. It can be used for
a wide range of purposes, from data mining to monitoring and automated testing.

For more information including a list of features check the Scrapy homepage at:
http://scrapy.org

Requirements
============

* Python 2.6 or up
* Works on Linux, Windows, Mac OSX, BSD

Install
=======

The quick way::

    pip install scrapy

For more details see the install section in the documentation:
http://doc.scrapy.org/en/latest/intro/install.html

Releases
========

You can download the latest stable and development releases from:
http://scrapy.org/download/

Documentation
=============

Documentation is available online at http://doc.scrapy.org/ and in the ``docs``
directory.

Community (blog, twitter, mail list, IRC)
=========================================

See http://scrapy.org/community/

Contributing
============

See http://doc.scrapy.org/en/latest/contributing.html

Companies using Scrapy
======================

See http://scrapy.org/companies/

Commercial Support
==================

See http://scrapy.org/support/
