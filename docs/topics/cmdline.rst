.. _topics-cmdline:

========================
Scrapy command line tool
========================

Scrapy is controlled through the ``scrapy`` command, which we'll refer to as
the "Scrapy tool" from now on to differentiate it from Scrapy commands.

The Scrapy tool provides several commands, for different purposes. Each command
supports its own particular syntax. In other words, each command supports a
different set of arguments and options.

This page doesn't describe each command and its syntax, but instead provides an
introduction to how the ``scrapy`` tool is used. After you learn the basics,
you can get help for each particular command using the ``scrapy`` tool itself.

Using the ``scrapy`` tool
=========================

The first thing you would do with the ``scrapy`` tool is to create your Scrapy
project::

    scrapy startproject myproject

That will create a Scrapy project under the ``myproject`` directory.

Next, you go inside the new project directory::

    cd myproject

And you're ready to use use the ``scrapy`` command to manage and control your
project from there. For example, to create a new spider::

    scrapy genspider mydomain mydomain.com

See all available commands
--------------------------

To see all available commands type::

    scrapy -h

That will print a summary of all available Scrapy commands.

The first line will print the currently active project, if you're inside a
Scrapy project.

Example (with an active project)::

    Scrapy X.X.X - project: myproject

    Usage
    =====

    ...

Example (with no active project)::

    Scrapy X.X.X - no active project

    Usage
    =====

    ...


Get help for a particular command
---------------------------------

To get help about a particular command, including its description, usage, and
available options type::

    scrapy <command> -h

Example::

    scrapy crawl -h

Using ``scrapy`` tool outside your project
==========================================

Not all commands must be run from "inside" a Scrapy project. You can, for
example, use the ``fetch`` command to download a page (using Scrapy built-in
downloader) from outside a project. Other commands that can be used outside a
project are ``startproject`` (obviously) and ``shell``, to launch a
:ref:`Scrapy Shell <topics-shell>`.

Also, keep in mind that some commands may have slightly different behaviours
when running them from inside projects. For example, the fetch command will use
spider arguments (such as ``user_agent`` attribute) if the url being fetched is
handled by some specific project spider that happens to define a custom
``user_agent`` attribute. This is feature, as the ``fetch`` command is meant to
download pages as they would be downloaded from the spider.
