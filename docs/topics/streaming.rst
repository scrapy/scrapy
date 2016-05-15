.. _topic-streaming:

=========
Streaming
=========

The Scrapy Streaming provides an interface to write spiders using any programming language,
using json objects to make requests, parse web contents, get data, and more.

Also, we officially provide helper libraries to develop your spiders using Java, JS, and R.

External Spiders
================

We define ``External Spider`` a spider developed in any programming language.

The external spider must communicate using the system ``stdin`` and ``stdout`` with the Streaming.

You can run standalone external spiders using the :command:`streaming` command.

If you want to integrate external spiders with a scrapy's project, create a file named ``external.json``
in your project root. This file must contain an array of json objects, each object with the ``name``
and ``command`` attributes.

The ``name`` attribute will be used as documented in the :ref:`topics-spiders-ref`.
The ``command`` is the path or name of the executable to run your spider.

For example, if you want to add spider developed in Java and a binary spider, you can define
the ``external.json`` as follows::

    [
      {
        "name": "java_spider",
        "command": "java /home/user/MySpider"
      },
      {
        "name": "compiled_spider",
        "command": "/home/user/my_executable"
      }
    ]



Communication Protocol
======================

The communication between your external spider and Scrapy Streaming will use json messages.

Every message must end with a line break ``\n``, and make sure to flush your process stdout after
sending every message to avoid buffering.


Sample Spider
-------------
TODO

Helper Libraries
================

TODO

Java
----

TODO

R
-

TODO

Java Script
-----------

TODO