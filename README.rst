.. image:: https://scrapy.org/img/scrapylogo.png
   :target: https://scrapy.org/
   
======
Scrapy
======

.. image:: https://img.shields.io/pypi/v/Scrapy.svg
   :target: https://pypi.python.org/pypi/Scrapy
   :alt: PyPI Version

.. image:: https://img.shields.io/pypi/pyversions/Scrapy.svg
   :target: https://pypi.python.org/pypi/Scrapy
   :alt: Supported Python Versions

.. image:: https://github.com/scrapy/scrapy/workflows/Ubuntu/badge.svg
   :target: https://github.com/scrapy/scrapy/actions?query=workflow%3AUbuntu
   :alt: Ubuntu

.. .. image:: https://github.com/scrapy/scrapy/workflows/macOS/badge.svg
   .. :target: https://github.com/scrapy/scrapy/actions?query=workflow%3AmacOS
   .. :alt: macOS


.. image:: https://github.com/scrapy/scrapy/workflows/Windows/badge.svg
   :target: https://github.com/scrapy/scrapy/actions?query=workflow%3AWindows
   :alt: Windows

.. image:: https://img.shields.io/badge/wheel-yes-brightgreen.svg
   :target: https://pypi.python.org/pypi/Scrapy
   :alt: Wheel Status

.. image:: https://img.shields.io/codecov/c/github/scrapy/scrapy/master.svg
   :target: https://codecov.io/github/scrapy/scrapy?branch=master
   :alt: Coverage report

.. image:: https://anaconda.org/conda-forge/scrapy/badges/version.svg
   :target: https://anaconda.org/conda-forge/scrapy
   :alt: Conda Version


Table of Contents
=================

.. contents::
   :depth: 2

Overview
========

Scrapy is a BSD-licensed fast high-level web crawling and web scraping framework, used to
crawl websites and extract structured data from their pages. It can be used for
a wide range of purposes, from data mining to monitoring and automated testing.

Scrapy is maintained by Zyte_ (formerly Scrapinghub) and `many other
contributors`_.

.. _many other contributors: https://github.com/scrapy/scrapy/graphs/contributors
.. _Zyte: https://www.zyte.com/

Check the Scrapy homepage at https://scrapy.org for more information,
including a list of features.


Requirements
============

* Python 3.8+
* Works on Linux, Windows, macOS, BSD


Install
=======

The quick way:

.. code:: bash

    pip install scrapy


How to install Scrapy on Ubuntu:

.. code:: bash

    sudo pip3 install scrapy
    or
    sudo apt-get install python3-scrapy

How to install Scrapy within a virtual environment:

.. code:: bash

    python3 -m venv scrapy-env
    source scrapy-env/bin/activate
    pip install scrapy

To check if Scrapy is installed:

.. code:: bash

    python3 -m scrapy
    or
    pip show scrapy

See the install section in the documentation at
https://docs.scrapy.org/en/latest/intro/install.html for more details.


Documentation
=============

Documentation is available online at https://docs.scrapy.org/ and in the ``docs``
directory.


Releases
========

You can check https://docs.scrapy.org/en/latest/news.html for the release notes.


Community (blog, twitter, mail list, IRC)
=========================================

See https://scrapy.org/community/ for details.


Community Resources
=========================================

Check out https://scrapeops.io/python-scrapy-playbook/ for guides and project examples.

Video tutorials are available at https://www.youtube.com/@scrapeops


Contributing
============

See https://docs.scrapy.org/en/master/contributing.html for details.


Code of Conduct
===============

Please note that this project is released with a Contributor `Code of Conduct <https://github.com/scrapy/scrapy/blob/master/CODE_OF_CONDUCT.md>`_.

By participating in this project you agree to abide by its terms.
Please report unacceptable behavior to opensource@zyte.com.


Companies using Scrapy
======================

See https://scrapy.org/companies/ for a list.


Commercial Support
==================

See https://scrapy.org/support/ for details.


Examples: Data mining using Scrapy
==================================

Using Scrapy to web scrape a chocolate e-commerce website: https://www.chocolate.co.uk/collections/all

Result: `Example Scraped Data CSV <https://github.com/DarrenChen2025/scrapy/blob/master/README%20resources/Example_Scraped_Data.csv>`_
