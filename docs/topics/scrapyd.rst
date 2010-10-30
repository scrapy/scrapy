.. _topics-scrapyd:

========================
Scrapy Service (scrapyd)
========================

.. versionadded:: 0.10

Scrapy comes with a built-in service, called "Scrapyd", which allows you to
deploy (aka. upload) your projects and control their spiders using a JSON web
service.

Projects and versions
=====================

Scrapyd can manage multiple projects and each project can have multiple
versions uploaded, but only the latest one will be used for launching new
spiders.

A common (and useful) convention to use for the version name is the revision
number of the version control tool you're using to track your Scrapy project
code. For example: ``r23``. The versions are not compared alphabetically but
using a smarter algorithm (the same `distutils`_ uses) so ``r10`` compares
greater to ``r9``, for example. 

How Scrapyd works
=================

Scrapyd is an application (typically run as a daemon) that continually polls
for projects that need to run (ie. those projects that have spiders enqueued).

When a project needs to run, a Scrapy process is started for that project using
something similar to the typical ``scrapy crawl``` command, and it continues to
run until it finishes processing all spiders form the spider queue.

Scrapyd also runs multiple processes in parallel, allocating them in a fixed
number of "slots", which defaults to the number of cpu processors available in
the system, but this can be changed with the ``max_proc`` option.  It also
starts as many processes as possible to handle the load.

In addition to dispatching and managing processes, Scrapyd provides a
:ref:`JSON web service <topics-scrapyd-jsonapi>` to upload new project versions
(as eggs) and schedule spiders. This feature is optional and can be disabled if
you want to implement your own custom Scrapyd. The components are pluggable and
can be changed, if you're familiar with the `Twisted Application Framework`_
which Scrapyd is implemented in.

Starting Scrapyd
================

Scrapyd is implemented using the standard `Twisted Application Framework`_. To
start the service, use the ``extras/scrapyd.tac`` file provided in the Scrapy
distribution, like this::

    twistd -ny extras/scrapyd.tac

That should get your Scrapyd started.

Installing Scrapyd
==================

How to deploy Scrapyd on your servers depends on the platform your're using.
Scrapy comes with Ubuntu packages for Scrapyd ready for deploying it as a
system service, to ease the installation and administration, but you can create
packages for other distribution or operating systems (including Windows). If
you do so, and want to contribute them, send a message to
scrapy-developers@googlegroups.com and say hi. The community will appreciate
it.

.. _topics-scrapyd-ubuntu:

Installing Scrapyd in Ubuntu
----------------------------

When deploying Scrapyd, it's very useful to have a version already packaged for
your system. For this reason, Scrapyd comes with Ubuntu packages ready to use
in your Ubuntu servers.

So, if you plan to deploy Scrapyd on a Ubuntu server, just add the Ubuntu
repositories as described in :ref:`topics-ubuntu` and then run::

    aptitude install scrapyd

This will install Scrapyd in your Ubuntu server creating a ``scrapy`` user
which Scrapyd will run as. It will also create some directories and files that
are listed below:

/etc/scrapyd
~~~~~~~~~~~~

Scrapyd configuration files. See :ref:`topics-scrapyd-config`.

/var/log/scrapyd/scrapyd.log
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Scrapyd main log file.

/var/log/scrapyd/scrapyd.out
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The standard output captured from Scrapyd process and any
sub-process spawned from it.

/var/log/scrapyd/scrapyd.err
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The standard error captured from Scrapyd and any sub-process spawned
from it. Remember to check this file if you're having problems, as the errors
may not get logged to the ``scrapyd.log`` file.

/var/log/scrapyd/slotN.log
~~~~~~~~~~~~~~~~~~~~~~~~~~

The log files of Scrapy processes started from Scrapyd, one per slot. These are
standard :ref:`Scrapy log files <topics-logging>`.

/var/lib/scrapyd/
~~~~~~~~~~~~~~~~~

Directory used to store data files (uploaded eggs and spider queues).

.. _topics-scrapyd-config:

Scrapyd Configuration file
==========================

Scrapyd searches for configuration files in the following locations, and parses
them in order with the latest ones taking more priority:

* ``/etc/scrapyd/scrapyd.conf`` (Unix)
* ``c:\scrapyd\scrapyd.conf`` (Windows)
* ``/etc/scrapyd/conf.d/*`` (in alphabetical order, Unix)
* ``scrapyd.conf``

The configuration file supports the following options (see default values in
the :ref:`example <topics-scrapyd-config-example>`).

http_port
---------

The TCP port where the HTTP JSON API will listen. Defaults to ``6800``.

max_proc
--------

The maximum number of concurrent Scrapy process that will be started. If unset
or ``0`` it will use the number of cpus available in the system.

debug
-----

Whether debug mode is enabled. Defaults to ``off``. When debug mode is enabled
the full Python traceback will be returned (as plain text responses) when there
is an error processing a JSON API call.

eggs_dir
--------

The directory where the project eggs will be stored.

dbs_dir
-------

The directory where the project databases will be stored (this includes the
spider queues).

logs_dir
--------

The directory where the Scrapy processes logs (``slotN.log``) will be stored.

egg_runner
----------

The module that will be used for launching sub-processes. You can customize the
Scrapy processes launched from Scrapyd by using your own module.

application
-----------

A function that returns the (Twisted) Application object to use. This can be
used if you want to extend Scrapyd by adding and removing your own components
and services.

For more info see `Twisted Application Framework`_

.. _topics-scrapyd-config-example:

Example configuration file
--------------------------

Here is an example configuration file with all the defaults:

.. literalinclude:: ../../scrapyd/default_scrapyd.conf

Eggifying your project
======================

In order to upload your project to Scrapyd, you must first build a `Python
egg`_ of it. This is called "eggifying" your project. You'll need to install
`setuptools`_ for this.

To eggify your project add a `setup.py`_ file to the root directory of your
project (where the ``scrapy.cfg`` resides) with the following contents::

    #!/usr/bin/env python

    from setuptools import setup, find_packages

    setup(
        name =          'myproject',
        version =       '1.0',
        packages =      find_packages(),
        entry_points =  {'scrapy': ['settings = myproject.settings']},
    )

And then the run the following command::

    python setup.py bdist_egg

This will generate an egg file and leave it in the ``dist`` directory, for
example::

    dist/myproject-1.0-py2.6.egg

Egg caveats
-----------

There are some things to keep in mind when building eggs of your Scrapy
project:

* make sure no local development settings are included in the egg when you
  build it. The ``find_packages`` function may be picking up your custom
  settings. In most cases you want to upload the egg with the default project
  settings.

* you shouldn't use ``__file__`` in your project code as it doesn't play well
  with eggs. Consider using `pkgutil.get_data()`_ instead.

* be careful when writing to disk in your project (in any spider, extension or
  middleware) as Scrapyd will probably run with a different user which may not
  have write access to certain directories. If you can, avoid writing to disk
  and always use `tempfile`_ for temporary files.

Uploading your project
======================

In these examples we'll be using `curl`_ for the web service interaction
examples, but you can use any command or library that speaks HTTP.

Once you've built the egg, you can upload your project to Scrapyd, like this::

    $ curl http://localhost:6800/addversion.json -F project=myproject -F version=r23 -F egg=@dist/myproject-1.0-py2.6.egg
    {"status": "ok", "spiders": ["spider1", "spider2", "spider3"]}

You'll see that the JSON response contains the spiders found in your project.

Scheduling a spider run
=======================

To schedule a spider run::

    $ curl http://localhost:6800/schedule.json -d project=myproject -d spider=spider2
    {"status": "ok"}

For more resources see: :ref:`topics-scrapyd-jsonapi` for more available resources.

.. _topics-scrapyd-jsonapi:

JSON API reference
==================

The following section describes the available resources in Scrapyd JSON API.

addversion.json
---------------

Add a version to a project, creating the project if it doesn't exist.

* Supported Request Methods: ``POST``
* Parameters:

  * ``project`` (string, required) - the project name
  * ``version`` (string, required) - the project version
  * ``egg`` (file, required) - a Python egg containing the project's code

Example request::

    $ curl http://localhost:6800/addversion.json -F project=myproject -F version=r23 -F egg=@myproject.egg

Example reponse::

    {"status": "ok", "spiders": ["spider1", "spider2", "spider3"]}

schedule.json
-------------

Schedule a spider run.

* Supported Request Methods: ``POST``
* Parameters:
  * ``project`` (string, required) - the project name
  * ``spider`` (string, required) - the spider name
  * any other parameter is passed as spider argument

Example request::

    $ curl http://localhost:6800/schedule.json -d project=myproject -d spider=somespider

Example response::

    {"status": "ok"}

listprojects.json
-----------------

Get the list of projects uploaded to this Scrapy server.

* Supported Request Methods: ``GET``
* Parameters: none

Example request::

    $ curl http://localhost:6800/listprojects.json

Example response::

    {"status": "ok", "projects": ["myproject", "otherproject"]}

listversions.json
-----------------

Get the list of versions available for some project. The versions are returned
in order, the last one is the currently used version.

* Supported Request Methods: ``GET``
* Parameters:
  * ``project`` (string, required) - the project name

Example request::

    $ curl http://localhost:6800/listversions.json?project=myproject

Example response::

    {"status": "ok", "versions": ["r99", "r156"]}

listspiders.json
----------------

Get the list of spiders available in the last version of some project.

* Supported Request Methods: ``GET``
* Parameters:
  * ``project`` (string, required) - the project name

Example request::

    $ curl http://localhost:6800/listspiders.json?project=myproject

Example response::

    {"status": "ok", "spiders": ["spider1", "spider2", "spider3"]}

delversion.json
---------------

Delete a project version. If there are no more versions available for a given
project, that project will be deleted too.

* Supported Request Methods: ``POST``
* Parameters:
  * ``project`` (string, required) - the project name
  * ``version`` (string, required) - the project version

Example request::

    $ curl http://localhost:6800/delversion.json -d project=myproject -d version=r99

Example response::

    {"status": "ok"}

delproject.json
---------------

Delete a project and all its uploaded versions.

* Supported Request Methods: ``POST``
* Parameters:
  * ``project`` (string, required) - the project name

Example request::

    $ curl http://localhost:6800/delproject.json -d project=myproject

Example response::

    {"status": "ok"}

.. _Python egg: http://peak.telecommunity.com/DevCenter/PythonEggs
.. _setup.py: http://docs.python.org/distutils/setupscript.html
.. _curl: http://en.wikipedia.org/wiki/CURL
.. _setuptools: http://pypi.python.org/pypi/setuptools
.. _pkgutil.get_data(): http://docs.python.org/library/pkgutil.html#pkgutil.get_data
.. _tempfile: http://docs.python.org/library/tempfile.html
.. _Twisted Application Framework: http://twistedmatrix.com/documents/current/core/howto/application.html
.. _distutils: http://docs.python.org/library/distutils.html
