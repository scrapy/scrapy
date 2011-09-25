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
for spiders that need to run.

When a spider needs to run, a process is started to crawl the spider::

    scrapy crawl myspider

Scrapyd also runs multiple processes in parallel, allocating them in a fixed
number of slots given by the `max_proc`_ and `max_proc_per_cpu`_ options,
starting as many processes as possible to handle the load.

In addition to dispatching and managing processes, Scrapyd provides a
:ref:`JSON web service <topics-scrapyd-jsonapi>` to upload new project versions
(as eggs) and schedule spiders. This feature is optional and can be disabled if
you want to implement your own custom Scrapyd. The components are pluggable and
can be changed, if you're familiar with the `Twisted Application Framework`_
which Scrapyd is implemented in.

Starting from 0.11, Scrapyd also provides a minimal :ref:`web interface
<topics-scrapyd-webui>`.

Starting Scrapyd
================

Scrapyd is implemented using the standard `Twisted Application Framework`_. To
start the service, use the ``extras/scrapyd.tac`` file provided in the Scrapy
distribution, like this::

    twistd -ny extras/scrapyd.tac

That should get your Scrapyd started.

Or, if you want to start Scrapyd from inside a Scrapy project you can use the
:command:`server` command, like this::

    scrapy server

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

    aptitude install scrapyd-0.13

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

/var/log/scrapyd/project
~~~~~~~~~~~~~~~~~~~~~~~~

Besides the main service log file, Scrapyd stores one log file per crawling
process in::

    /var/log/scrapyd/PROJECT/SPIDER/ID.log

Where ``ID`` is a unique id for the run.

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
or ``0`` it will use the number of cpus available in the system mulitplied by
the value in ``max_proc_per_cpu`` option. Defaults to ``0``.

max_proc_per_cpu
----------------

The maximum number of concurrent Scrapy process that will be started per cpu.
Defaults to ``4``.

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

The directory where the Scrapy processes logs will be stored.

logs_to_keep
------------

The number of logs to keep per spider. Defaults to ``5``.

runner
------

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

.. _topics-deploying:

Deploying your project
======================

Deploying your project into a Scrapyd server typically involves two steps:

1. building a `Python egg`_ of your project. This is called "eggifying" your
   project. You'll need to install `setuptools`_ for this. See
   :ref:`topics-egg-caveats` below.

2. uploading the egg to the Scrapyd server

The simplest way to deploy your project is by using the :command:`deploy`
command, which automates the process of building the egg uploading it using the
Scrapyd HTTP JSON API.

The :command:`deploy` command supports multiple targets (Scrapyd servers that
can host your project) and each target supports multiple projects.

Each time you deploy a new version of a project, you can name it for later
reference.

Show and define targets
-----------------------

To see all available targets type::

    scrapy deploy -l

This will return a list of available targets and their URLs. For example::

    scrapyd              http://localhost:6800/

You can define targets by adding them to your project's ``scrapy.cfg`` file,
or any other supported location like ``~/.scrapy.cfg``, ``/etc/scrapy.cfg``,
or ``c:\scrapy\scrapy.cfg`` (in Windows).

Here's an example of defining a new target ``scrapyd2`` with restricted access
through HTTP basic authentication::

    [deploy:scrapyd2]
    url = http://scrapyd.mydomain.com/api/scrapyd/
    username = john
    password = secret

.. note:: The :command:`deploy` command also supports netrc for getting the
   credentials.

Now, if you type ``scrapy deploy -l`` you'll see::

    scrapyd              http://localhost:6800/
    scrapyd2             http://scrapyd.mydomain.com/api/scrapyd/

See available projects
----------------------

To see all available projets in a specific target use::

    scrapy deploy -L scrapyd

It would return something like this::

    project1
    project2

Deploying a project
-------------------

Finally, to deploy your project use::

    scrapy deploy scrapyd -p project1

This will eggify your project and upload it to the target, printing the JSON
response returned from the Scrapyd server. If you have a ``setup.py`` file in
your project, that one will be used. Otherwise a ``setup.py`` file will be
created automatically (based on a simple template) that you can edit later.

After running that command you will see something like this, meaning your
project was uploaded successfully::

    Deploying myproject-1287453519 to http://localhost:6800/addversion.json
    Server response (200):
    {"status": "ok", "spiders": ["spider1", "spider2"]}

By default ``scrapy deploy`` uses the current timestamp for generating the
project version, as you can see in the output above. However, you can pass a
custom version with the ``--version`` option::

    scrapy deploy scrapyd -p project1 --version 54

Also, if you use Mercurial for tracking your project source code, you can use
``HG`` for the version which will be replaced by the current Mercurial
revision, for example ``r382``::

    scrapy deploy scrapyd -p project1 --version HG

And, if you use Git for tracking your project source code, you can use
``GIT`` for the version which will be replaced by the SHA1 of current Git
revision, for example ``b0582849179d1de7bd86eaa7201ea3cda4b5651f``::

    scrapy deploy scrapyd -p project1 --version GIT

Support for other version discovery sources may be added in the future.

Finally, if you don't want to specify the target, project and version every
time you run ``scrapy deploy`` you can define the defaults in the
``scrapy.cfg`` file. For example::

    [deploy]
    url = http://scrapyd.mydomain.com/api/scrapyd/
    username = john
    password = secret
    project = project1
    version = HG

This way, you can deploy your project just by using::

    scrapy deploy

Local settings
--------------

Sometimes, while your working on your projects, you may want to override your
certain settings with certain local settings that shouldn't be deployed to
Scrapyd, but only used locally to develop and debug your spiders.

One way to deal with this is to have a ``local_settings.py`` at the root of
your project (where the ``scrapy.cfg`` file resides) and add these lines to the
end of your project settings::

    try:
        from local_settings import *
    except ImportError:
        pass

``scrapy deploy`` won't deploy anything outside the project module so the
``local_settings.py`` file won't be deployed.

Here's the directory structure, to illustrate::

    scrapy.cfg
    local_settings.py
    myproject/
        __init__.py
        settings.py
        spiders/
            ...

.. _topics-egg-caveats:

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

Scheduling a spider run
=======================

To schedule a spider run::

    $ curl http://localhost:6800/schedule.json -d project=myproject -d spider=spider2
    {"status": "ok", "jobid": "26d1b1a6d6f111e0be5c001e648c57f8"}

For more resources see: :ref:`topics-scrapyd-jsonapi` for more available resources.

.. _topics-scrapyd-webui:

Web Interface
=============

.. versionadded:: 0.11

Scrapyd comes with a minimal web interface (for monitoring running processes
and accessing logs) which can be accessed at http://localhost:6800/

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

    {"status": "ok", "spiders": 3}

schedule.json
-------------

Schedule a spider run.

* Supported Request Methods: ``POST``
* Parameters:
  * ``project`` (string, required) - the project name
  * ``spider`` (string, required) - the spider name
  * ``setting`` (string, optional) - a scrapy setting to use when running the spider
  * any other parameter is passed as spider argument

Example request::

    $ curl http://localhost:6800/schedule.json -d project=myproject -d spider=somespider

Example response::

    {"status": "ok"}

Example request passing a spider argument (``arg1``) and a setting
(:setting:`DOWNLOAD_DELAY`)::

    $ curl http://localhost:6800/schedule.json -d project=myproject -d spider=somespider -d setting=DOWNLOAD_DELAY=2 -d arg1=val1


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
