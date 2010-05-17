======================
Contributing to Scrapy
======================

There are many ways to contribute to Scrapy. Here are some of them:

* Blog about Scrapy. Tell the world how you're using Scrapy. This will help
  newcomers with more examples and the Scrapy project to increase its
  visibility.

* Report bugs and request features in our `ticket tracker`_, trying to follow
  the guidelines detailed in `Reporting bugs`_ below.

* Submit patches for new functionality and/or bug fixes. Please read
  `Submitting patches`_ below for details on how to submit a patch.

* Join the `scrapy-developers`_ mailing list and share your ideas on how to
  improve Scrapy. We're always open to suggestions.

Reporting bugs
==============

Well-written bug report are very helpful, so keep in mind the following
guidelines when reporting a new bug.

* check the :ref:`FAQ <faq>` first to see if your issue is addressed in a
  well-known question

* `search the issue tracker` to see if your issues has already been reported.
  If it has, don't dismiss the report but check the ticket history and
  comments, you may have additional useful information to contribute.

* search the `scrapy-users` list to see if it has been discussed there, or
  if you're not sure if what you're seeing is a bug. You can also ask in the
  `#scrapy` IRC channel.

* write complete, reproducible, specific bug reports. The smaller the test
  case, the better. Remember that other developers won't have your project to
  reproduce the bug, so please include all relevant files required to reproduce
  it.

Submitting patches
==================

The better written a patch is, the higher chance that it'll get accepted and
the sooner that will be merged.

Well-written patches should:

* contain the minimum amount of code required for the specific change. Small
  patches are easier to review and merge. So, if you're doing more than one
  change (or bug fix), please consider submitting one patch per change. Do not
  collapse multiple changes into a single patch. For big changes consider using
  a patch queue.

* pass all unit-tests. See `Running tests` below.

* include one (or more) test cases that check the bug fixed or the new
  functionality added. See `Writing tests`_ below.

* if you're adding or changing a public (documented) API, please include 
  the proper update to the documentation.  See `Documentation policies`_ below.

To submit patches, you can follow any of these mechanisms:

* create appropriate tickets in the issue tracker and attach the patches to
  those tickets. The patches can be generated using ``hg diff``.

* send the patches to the `scrapy-developers` list, along with a comment
  explaining what was fixed or the new functionality (what it is, why it's
  needed, etc). The more info you include, the easier will be for core
  developers to understand and accept your patch.

* fork the `Github mirror`_ and send a pull request when you're done working on
  the patch

* clone the `Bitbucket mirror`_ and send a pull request when you're done
  working on the patch

You can also discuss the new functionality (or bug fix) in `scrapy-developers`
first, before creating the patch, but it's always good to have a patch ready to
illustrate your arguments and show that you have put some additional thought
into the subject.

Coding style
============

Please follow these coding conventions when writing code for inclusion in
Scrapy:

* Unless otherwise specified, follow :pep:`8`.

* It's OK to use lines longer than 80 chars if it improves the code
  readability.

* Please don't put your name in the code you contribute. Our policy is to keep
  contributor's name in ``AUTHORS`` file distributed with Scrapy.

Documentation policies
======================

* **Don't** use docstrings for documenting classes, or methods which are
  already documented in the official (sphinx) documentation. For example, the
  :meth:`ItemLoader.add_value` method should be documented in the sphinx
  documentation and not its docstring.

* **Do** use docstrings for documenting functions not present in the official
  (sphinx) documentation, such as functions from ``scrapy.utils`` package and
  sub-modules.

Tests
=====

Tests are implemented using the `Twisted unit-testing framework` called
``trial``.

Running tests
-------------

To run all tests go to the root directory of Scrapy source code and run:

    ``bin/runtests.sh`` (on unix)

    ``bin/runtests.bat`` (on windows)

To run a specific test (say ``scrapy.tests.test_contrib_loader``) use:

    ``bin/runtests.sh scrapy.tests.test_contrib_loader`` (on unix)

    ``bin/runtests.bat scrapy.tests.test_contrib_loader`` (on windows)

Writing tests
-------------

All functionality (including new features and bug fixes) must include a test
case to check it, so please include tests for your patches if you want them to
get accepted sooner.

Scrapy uses unit-tests, which are located in the ``scrapy.tests`` package
(``scrapy/tests`` directory). Their module name typically resembles the full
path of the module they're testing. For example, the item loaders code is in::

    scrapy.contrib.loader

And their unit-tests are in::

    scrapy.tests.test_contrib_loader

.. _ticket tracker: http://dev.scrapy.org/newticket
.. _scrapy-users: http://groups.google.com/group/scrapy-users
.. _scrapy-developers: http://groups.google.com/group/scrapy-developers
.. _Github mirror: http://github.com/insophia/scrapy/
.. _Bitbucket mirror: http://bitbucket.org/insophia/scrapy/
.. _Twisted unit-testing framework: http://twistedmatrix.com/documents/current/core/development/policy/test-standard.html
