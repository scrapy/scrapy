.. _intro-tutorial1:

======================
Creating a new project
======================

.. highlight:: sh

In this tutorial, we'll teach you how to scrape http://www.google.com/dirhp Google's web directory.

We'll assume that Scrapy is already installed in your system, if not see :ref:`intro-install`.

For starting a new project, enter the directory where you'd like your project to be located, and run::

    $ scrapy-admin.py startproject google

As long as Scrapy is well installed and the path is set, this should create a directory called "google" containing the following files:

* *scrapy-ctl.py* - the project's control script. It's used for running the different tasks (like "genspider", "crawl" and "parse"). We'll talk more about this later.
* *scrapy_settings.py* - the project's settings file.
* *items.py* - were you define the different kinds of items you're going to scrape.
* *spiders* - directory where you'll later place your spiders.
* *templates* - directory containing some templates for newly created spiders, and where you can put your own.

| Ok, now that you have your project's structure defined, the last thing to do is to set your PYTHONPATH to your project's directory.
| You can do this by adding this to your .bashrc file:

::

    $ export PYTHONPATH=/path/to/your/project

Now you can continue with the next part of the tutorial: :ref:`intro-tutorial2`.
