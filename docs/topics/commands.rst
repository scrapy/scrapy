.. _topics-commands:

=================
Command line tool
=================

Scrapy is controlled through the ``scrapy`` command-line tool, to be referred
here as the "Scrapy tool" to differentiate it from their sub-commands which we
just call "commands", or "Scrapy commands".

The Scrapy tool provides several commands, for multiple purposes, and each one
accepts a different set of arguments and options.

Using the ``scrapy`` tool
=========================

You can start by running the Scrapy tool with no arguments and it will print
some usage help and the available commands::

    Scrapy X.Y - no active project

    Usage
    =====

    To run a command:
      scrapy <command> [options] [args]

    To get help:
      scrapy <command> -h

    Available commands
    ==================

    [...]

The first line will print the currently active project, if you're inside a
Scrapy project. In this, it was run from outside a project. If run from inside
a project it would have printed something like this::

    Scrapy X.Y - project: myproject

    Usage
    =====

    [...]

Using the ``scrapy`` tool to create projects
============================================

The first thing you typically do with the ``scrapy`` tool is create your Scrapy
project::

    scrapy startproject myproject

That will create a Scrapy project under the ``myproject`` directory.

Next, you go inside the new project directory::

    cd myproject

And you're ready to use use the ``scrapy`` command to manage and control your
project from there.

Using the ``scrapy`` tool to control projects
=============================================

You use the ``scrapy`` tool from inside your projects to control and manage
them.

For example, to create a new spider::

    scrapy genspider mydomain mydomain.com

Some Scrapy commands (like :command:`crawl`) must be run from inside a Scrapy
project. See the :ref:`commands reference <topics-commands-ref>` below for more
information on which commands must be run from inside projects, and which not.

Also keep in mind that some commands may have slightly different behaviours
when running them from inside projects. For example, the fetch command will use
spider-overridden behaviours (such as custom ``user_agent`` attribute) if the
url being fetched is associated with some specific spider. This is intentional,
as the ``fetch`` command is meant to be used to check how spiders are
downloading pages.

.. _topics-commands-ref:

Available tool commands
=======================

Here's a list of available built-in commands with a description and some usage
examples. Remember you can always get more info about each command by running::

    scrapy <command> -h

And you can check all available commands with::

    scrapy -h

.. command:: startproject

startproject
------------

+-------------------+----------------------------------------+
| Syntax:           | ``scrapy startproject <project_name>`` |
+-------------------+----------------------------------------+
| Requires project: | *no*                                   |
+-------------------+----------------------------------------+

Creates a new Scrapy project named ``project_name``, under the ``project_name``
directory.

Usage example::

    $ scrapy startproject myproject

.. command:: genspider

genspider
---------

+-------------------+--------------------------------------+
| Syntax:           | ``scrapy genspider <name> <domain>`` |
+-------------------+--------------------------------------+
| Requires project: | *yes*                                |
+-------------------+--------------------------------------+

Create a new spider in the current project.

This is just a convenient shortcut command for creating spiders based on
pre-defined templates, but certainly not the only way to create spiders. You
can just create the spider source code files yourself.

Usage example::

    $ scrapy genspider example example.com
    Created spider 'example' using template 'crawl' in module:
      jobsbot.spiders.example

.. command:: crawl

crawl
-----

+-------------------+-------------------------------+
| Syntax:           | ``scrapy crawl <spider|url>`` |
+-------------------+-------------------------------+
| Requires project: | *yes*                         |
+-------------------+-------------------------------+

Start crawling a spider. If a URL is passed instead of a spider, it will start
from that URL instead of the spider start urls.

Usage examples::

    $ scrapy crawl example.com
    [ ... example.com spider starts crawling ... ]

    $ scrapy crawl myspider
    [ ... myspider starts crawling ... ]

    $ scrapy crawl http://example.com/some/page.html
    [ ... spider that handles example.com starts crawling from that url ... ]

.. command:: start

start
-----

+-------------------+------------------+
| Syntax:           | ``scrapy start`` |
+-------------------+------------------+
| Requires project: | *yes*            |
+-------------------+------------------+

Start Scrapy in server mode.

Usage example::

    $ scrapy start
    [ ... scrapy starts and stays idle waiting for spiders to get scheduled ... ]

.. command:: list

list
----

+-------------------+-----------------+
| Syntax:           | ``scrapy list`` |
+-------------------+-----------------+
| Requires project: | *yes*           |
+-------------------+-----------------+

List all available spiders in the current project. The output is one spider per
line.

Usage example::

    $ scrapy list
    spider1
    spider2

.. command:: fetch

fetch
-----

+-------------------+------------------------+
| Syntax:           | ``scrapy fetch <url>`` |
+-------------------+------------------------+
| Requires project: | *no*                   |
+-------------------+------------------------+

Downloads the given URL using the Scrapy downloader and writes the contents to
standard output.

The interesting thing about this command is that it fetches the page how the
the spider would download it. For example, if the spider has an ``user_agent``
attribute which overrides the User Agent, it will use that one.

So this command can be used to "see" how your spider would fetch certain page.

If used outside a project, no particular per-spider behaviour would be applied
and it will just use the default Scrapy downloder settings.

Usage examples::

    $ scrapy fetch --nolog http://www.example.com/some/page.html
    [ ... html content here ... ]

    $ scrapy fetch --nolog --headers http://www.example.com/
    {'Accept-Ranges': ['bytes'],
     'Age': ['1263   '],
     'Connection': ['close     '],
     'Content-Length': ['596'],
     'Content-Type': ['text/html; charset=UTF-8'],
     'Date': ['Wed, 18 Aug 2010 23:59:46 GMT'],
     'Etag': ['"573c1-254-48c9c87349680"'],
     'Last-Modified': ['Fri, 30 Jul 2010 15:30:18 GMT'],
     'Server': ['Apache/2.2.3 (CentOS)']}

.. command:: view

view
----

+-------------------+-----------------------+
| Syntax:           | ``scrapy view <url>`` |
+-------------------+-----------------------+
| Requires project: | *no*                  |
+-------------------+-----------------------+

Opens the given URL in a browser, as your Scrapy spider would "see" it.
Sometimes spiders see pages differently from regular users, so this can be used
to check what the spider "sees" and confirm it's what you expect.

Usage example::

    $ scrapy view http://www.example.com/some/page.html
    [ ... browser starts ... ]

.. command:: shell

shell
-----

+-------------------+------------------------+
| Syntax:           | ``scrapy shell [url]`` |
+-------------------+------------------------+
| Requires project: | *no*                   |
+-------------------+------------------------+

Starts the Scrapy shell for the given URL (if given) or empty if not URL is
given. See :ref:`topics-shell` for more info.

Usage example::

    $ scrapy shell http://www.example.com/some/page.html
    [ ... scrapy shell starts ... ]

.. command:: parse

parse
-----

+-------------------+----------------------------------+
| Syntax:           | ``scrapy parse <url> [options]`` |
+-------------------+----------------------------------+
| Requires project: | *yes*                            |
+-------------------+----------------------------------+

Fetches the given URL and parses with the spider that handles it, using the
method passed with the ``--callback`` option, or ``parse`` if not given.

Supported options:

 * ``--callback`` or ``-c``: spider method to use as callback for parsing the
   response

 * ``--noitems``: don't show extracted links

 * ``--nolinks``: don't show scraped items

Usage example::

    $ scrapy parse http://www.example.com/ -c parse_item
    [ ... scrapy log lines crawling example.com spider ... ]
    # Scraped Items - callback: parse ------------------------------------------------------------
    MyItem({'name': u"Example item",
     'category': u'Furniture',
     'length': u'12 cm'}
    )

.. command:: settings

settings
--------

+-------------------+-------------------------------+
| Syntax:           | ``scrapy settings [options]`` |
+-------------------+-------------------------------+
| Requires project: | *no*                          |
+-------------------+-------------------------------+

Get the value of a Scrapy setting.

If used inside a project it'll show the project setting value, otherwise it'll
show the default Scrapy value for that setting.

Example usage::

    $ scrapy settings --get BOT_NAME
    scrapybot
    $ scrapy settings --get DOWNLOAD_DELAY
    0

.. command:: runspider

runspider
---------

+-------------------+---------------------------------------+
| Syntax:           | ``scrapy runspider <spider_file.py>`` |
+-------------------+---------------------------------------+
| Requires project: | *no*                                  |
+-------------------+---------------------------------------+

Run a spider self-contained in a Python file, without having to create a
project.

Example usage::

    $ scrapy runspider myspider.py
    [ ... spider starts crawling ... ]
