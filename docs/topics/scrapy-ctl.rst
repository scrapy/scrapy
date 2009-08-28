.. _topics-scrapy-ctl:

=============
scrapy-ctl.py
=============

Scrapy is controlled through the ``scrapy-ctl.py`` control script. The script
provides several commands, for different purposes. Each command supports its
own particular syntax. In other words, each command supports a different set of
arguments and options.

This page doesn't describe each command and its syntax, but provides an
introduction to how the ``scrapy-ctl.py`` script is used. After you learn how
to use it, you can get help for each particular command using the same
``scrapy-ctl.py`` script.

Global and project-specific ``scrapy-ctl.py``
=============================================

There is one global ``scrapy-ctl.py`` script shipped with Scrapy and another
``scrapy-ctl.py`` script automatically created inside your Scrapy project. The
project-specific ``scrapy-ctl.py`` is just a thin wrapper around the global
``scrapy-ctl.py`` which populates the settings of your project, so you don't
have to specify them every time through the ``--settings`` argument.

Using the ``scrapy-ctl.py`` script
==================================

The first thing you would do with the ``scrapy-ctl.py`` script is create your
Scrapy project::

    scrapy-ctl.py startproject myproject

That will create a Scrapy project under the ``myproject`` directory and will
put a new ``scrapy-ctl.py`` inside that directory.

So, you go inside the new project directory::

    cd myproject

And you're ready to use your project's ``scrapy-ctl.py``. For example, to
create a new spider::

    python scrapy-ctl.py genspider mydomain mydomain.com

This is the same as using the global ``scrapy-ctl.py`` script and passing the
project settings module in the ``--settings`` argument::

    scrapy-ctl.py --settings=myproject.settings genspider mydomain mydomain.com

You'll typically use the project-specific ``scrapy-ctl.py``, for convenience.

See all available commands
--------------------------

To see all available commands type::

    scrapy-ctl.py -h

That will print a summary of all available Scrapy commands.

The first line will print the currently active project (if any). 

Example (active project)::

    Scrapy 0.7.0 - project: myproject

    Usage
    =====

    ...

Example (no active project)::

    Scrapy 0.7.0 - no active project

    Usage
    =====

    ...


Get help for a particular command
---------------------------------

To get help about a particular command, including its description, usage and
available options type::

    scrapy-ctl.py <command> -h

Example::

    scrapy-ctl.py crawl -h

Using ``scrapy-ctl.py`` outside your project
============================================

Not all commands must be run from "inside" a Scrapy project. You can, for
example, use the ``fetch`` command to download a page (using Scrapy built-in
downloader) from outside a project. Other commands that can be used outside a
project are ``startproject`` (obviously) and ``shell``, to launch a
:ref:`Scrapy Shell <topics-shell>`.

