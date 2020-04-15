:orphan:

======================================
Scrapy documentation quick start guide
======================================

This file provides a quick guide on how to compile the Scrapy documentation.


Setup the environment
---------------------

To compile the documentation you need Sphinx Python library. To install it
and all its dependencies run the following command from this dir

::

    pip install -r requirements.txt


Compile the documentation
-------------------------

To compile the documentation (to classic HTML output) run the following command
from this dir::

    make html

Documentation will be generated (in HTML format) inside the ``build/html`` dir.


View the documentation
----------------------

To view the documentation run the following command::

    make htmlview

This command will fire up your default browser and open the main page of your
(previously generated) HTML documentation.


Start over
----------

To cleanup all generated documentation files and start from scratch run::

    make clean

Keep in mind that this command won't touch any documentation source files.


Recreating documentation on the fly
-----------------------------------

There is a way to recreate the doc automatically when you make changes, you
need to install watchdog (``pip install watchdog``) and then use::

    make watch
