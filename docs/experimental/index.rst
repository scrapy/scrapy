.. _experimental:

Experimental features
=====================

This section documents experimental Scrapy features that may become stable in
future releases, but whose API is not yet stable. Use them with caution, and
subscribe to the `mailing lists <http://scrapy.org/community/>`_ to get
notified of any changes. 

Since it's not revised so frequently, this section may contain documentation
which is outdated, incomplete or overlapping with stable documentation (until
it's properly merged) . Use at your own risk.

.. warning::

   This documentation is a work in progress. Use at your own risk.

Add commands using external libraries
-------------------------------------

You can also add Scrapy commands from an external library by adding `scrapy.commands` section into entry_points in the `setup.py`.

The following example adds `my_command` command::

  from setuptools import setup, find_packages

  setup(name='scrapy-mymodule',
    entry_points={
      'scrapy.commands': [
        'my_command=my_scrapy_module.commands:MyCommand',
      ],
    },
   )
