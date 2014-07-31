.. _topics-contributing:

======================
Contributing to Scrapy
======================

There are many ways to contribute to Scrapy. Here are some of them:

* Blog about Scrapy. Tell the world how you're using Scrapy. This will help
  newcomers with more examples and the Scrapy project to increase its
  visibility.

* Report bugs and request features in the `issue tracker`_, trying to follow
  the guidelines detailed in `Reporting bugs`_ below.

* Submit patches for new functionality and/or bug fixes. Please read
  `Writing patches`_ and `Submitting patches`_ below for details on how to
  write and submit a patch.

* Join the `scrapy-users`_ mailing list and share your ideas on how to
  improve Scrapy. We're always open to suggestions.

Reporting bugs
==============

.. note::

    Please report security issues **only** to
    scrapy-security@googlegroups.com. This is a private list only open to
    trusted Scrapy developers, and its archives are not public.

Well-written bug reports are very helpful, so keep in mind the following
guidelines when reporting a new bug.

* check the :ref:`FAQ <faq>` first to see if your issue is addressed in a
  well-known question

* check the `open issues`_ to see if it has already been reported. If it has,
  don't dismiss the report but check the ticket history and comments, you may
  find additional useful information to contribute.

* search the `scrapy-users`_ list to see if it has been discussed there, or
  if you're not sure if what you're seeing is a bug. You can also ask in the
  `#scrapy` IRC channel.

* write complete, reproducible, specific bug reports. The smaller the test
  case, the better. Remember that other developers won't have your project to
  reproduce the bug, so please include all relevant files required to reproduce
  it.

* include the output of ``scrapy version -v`` so developers working on your bug
  know exactly which version and platform it occurred on, which is often very
  helpful for reproducing it, or knowing if it was already fixed.

Writing patches
===============

The better written a patch is, the higher chance that it'll get accepted and
the sooner that will be merged.

Well-written patches should:

* contain the minimum amount of code required for the specific change. Small
  patches are easier to review and merge. So, if you're doing more than one
  change (or bug fix), please consider submitting one patch per change. Do not
  collapse multiple changes into a single patch. For big changes consider using
  a patch queue.

* pass all unit-tests. See `Running tests`_ below.

* include one (or more) test cases that check the bug fixed or the new
  functionality added. See `Writing tests`_ below.

* if you're adding or changing a public (documented) API, please include
  the documentation changes in the same patch.  See `Documentation policies`_
  below.

Submitting patches
==================

The best way to submit a patch is to issue a `pull request`_ on Github,
optionally creating a new issue first.

Remember to explain what was fixed or the new functionality (what it is, why
it's needed, etc). The more info you include, the easier will be for core
developers to understand and accept your patch.

You can also discuss the new functionality (or bug fix) before creating the
patch, but it's always good to have a patch ready to illustrate your arguments
and show that you have put some additional thought into the subject. A good
starting point is to send a pull request on Github. It can be simple enough to
illustrate your idea, and leave documentation/tests for later, after the idea
has been validated and proven useful. Alternatively, you can send an email to
`scrapy-users`_ to discuss your idea first.

Finally, try to keep aesthetic changes (:pep:`8` compliance, unused imports
removal, etc) in separate commits than functional changes. This will make pull
requests easier to review and more likely to get merged.

Coding style
============

Please follow these coding conventions when writing code for inclusion in
Scrapy:

* Unless otherwise specified, follow :pep:`8`.

* It's OK to use lines longer than 80 chars if it improves the code
  readability.

* Don't put your name in the code you contribute. Our policy is to keep
  the contributor's name in the `AUTHORS`_ file distributed with Scrapy.

Scrapy Contrib
==============

Scrapy contrib shares a similar rationale as Django contrib, which is explained
in `this post <http://jacobian.org/writing/what-is-django-contrib/>`_. If you
are working on a new functionality, please follow that rationale to decide
whether it should be a Scrapy contrib. If unsure, you can ask in
`scrapy-users`_.

Documentation policies
======================

* **Don't** use docstrings for documenting classes, or methods which are
  already documented in the official (sphinx) documentation. For example, the
  :meth:`ItemLoader.add_value` method should be documented in the sphinx
  documentation, not its docstring.

* **Do** use docstrings for documenting functions not present in the official
  (sphinx) documentation, such as functions from ``scrapy.utils`` package and
  its sub-modules.

Tests
=====

Tests are implemented using the `Twisted unit-testing framework`_, running
tests requires `tox`_.

Running tests
-------------

To run all tests go to the root directory of Scrapy source code and run:

    ``tox``

To run a specific test (say ``tests/test_contrib_loader.py``) use:

    ``tox -- tests/test_contrib_loader.py``


Writing tests
-------------

All functionality (including new features and bug fixes) must include a test
case to check that it works as expected, so please include tests for your
patches if you want them to get accepted sooner.

Scrapy uses unit-tests, which are located in the `tests/`_ directory.
Their module name typically resembles the full path of the module they're
testing. For example, the item loaders code is in::

    scrapy.contrib.loader

And their unit-tests are in::

    tests/test_contrib_loader.py

.. _issue tracker: https://github.com/scrapy/scrapy/issues
.. _scrapy-users: http://groups.google.com/group/scrapy-users
.. _Twisted unit-testing framework: http://twistedmatrix.com/documents/current/core/development/policy/test-standard.html
.. _AUTHORS: https://github.com/scrapy/scrapy/blob/master/AUTHORS
.. _tests/: https://github.com/scrapy/scrapy/tree/master/tests
.. _open issues: https://github.com/scrapy/scrapy/issues
.. _pull request: http://help.github.com/send-pull-requests/
.. _tox: https://pypi.python.org/pypi/tox
