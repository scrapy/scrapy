.. _topics-scripts:

==================
Management scripts
==================

Scrapy is controlled by two commmandline scripts:

1. :ref:`topics-scripts-scrapy-admin`: used to create Scrapy projects.  
2. :ref:`topics-scripts-scrapy-ctl`: located in every project's root dir, used
   to manage each project.

.. _topics-scripts-scrapy-admin:

scrapy-admin.py
===============
Usage: ``scrapy-admin.py <subcommand>``

This script should be in your system path.

Available subcommands
---------------------

startproject
~~~~~~~~~~~~
Usage: ``startproject <project_name>``

Starts a new project with name ``project_name``


.. _topics-scripts-scrapy-ctl:

scrapy-ctl.py
=============
Usage: ``scrapy-admin.py <subcommand>``

This script is located in every project's root folder.


Available subcommands
---------------------

crawl
~~~~~
Usage: ``crawl [options] <domain|url> ...``

Start crawling a domain or URL


``--nopipeline``
""""""""""""""""
disable scraped item pipeline

``--restrict``
""""""""""""""
restrict crawling only to the given urls

``-n, --nofollow``
""""""""""""""""""
don't follow links (for use with URLs only)

``-c, --callback``
""""""""""""""""""
use the provided callback for starting to crawl the given url


fetch
~~~~~
Usage: ``fetch <url>``

Fetch a URL using the Scrapy downloader and print its content to stdout. You
may want to use --nolog to disable logging.


``--headers``
"""""""""""""
print HTTP headers instead of body


genspider
~~~~~~~~~
Usage: ``genspider [options] <spider_module_name> <spider_domain_name>``


``--template``
""""""""""""""
Default: ``crawl``

uses a custom template.

``--force``
"""""""""""
if the spider already exists, overwrite it with the template.

``--list``
~~~~~~~~~~
list available templates

``--dump``
""""""""""""""
dump ``--template`` to stdout


help
~~~~
Usage: ``help <command>``

Provides extended help for the given command.


list
~~~~
List available spiders.


parse
~~~~~
Usage: ``parse [options] <url>``

Parse the given URL (using the spider) and print the results.


``--nolinks``
"""""""""""""
don't show extracted links

``--noitems``
"""""""""""""
don't show scraped items

``--nocolour``
""""""""""""""
avoid using pygments to colorize the output

``-r, --rules``
"""""""""""""""
try to match and parse the url with the defined rules (if any)

``-c, --callbacks``
"""""""""""""""""""
use the provided callback(s) for parsing the url (separated with commas)


shell
~~~~~
Usage: ``shell [options] <url>``

Interactive console for scraping the given url. For scraping local files you
can use a URL like ``file://path/to/file.html``. See :ref:`topics-shell` for
usage documentation.


start
~~~~~
Start the Scrapy manager but don't run any spider (idle mode)

