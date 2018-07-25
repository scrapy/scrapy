.. _topics-contributing:

======================
Contributing to Scrapy
======================

.. important::

    Double check that you are reading the most recent version of this document at
    https://doc.scrapy.org/en/master/contributing.html

There are many ways to contribute to Scrapy. Here are some of them:

* Blog about Scrapy. Tell the world how you're using Scrapy. This will help
  newcomers with more examples and will help the Scrapy project to increase its
  visibility.

* Report bugs and request features in the `issue tracker`_, trying to follow
  the guidelines detailed in `Reporting bugs`_ below.

* Submit patches for new functionalities and/or bug fixes. Please read
  :ref:`writing-patches` and `Submitting patches`_ below for details on how to
  write and submit a patch.

* Join the `Scrapy subreddit`_ and share your ideas on how to
  improve Scrapy. We're always open to suggestions.

* Answer Scrapy questions at
  `Stack Overflow <https://stackoverflow.com/questions/tagged/scrapy>`__.


Reporting bugs
==============

.. note::

    Please report security issues **only** to
    scrapy-security@googlegroups.com. This is a private list only open to
    trusted Scrapy developers, and its archives are not public.

Well-written bug reports are very helpful, so keep in mind the following
guidelines when you're going to report a new bug.

* check the :ref:`FAQ <faq>` first to see if your issue is addressed in a
  well-known question

* if you have a general question about scrapy usage, please ask it at
  `Stack Overflow <https://stackoverflow.com/questions/tagged/scrapy>`__
  (use "scrapy" tag).

* check the `open issues`_ to see if the issue has already been reported. If it
  has, don't dismiss the report, but check the ticket history and comments. If 
  you have additional useful information, please leave a comment, or consider
  :ref:`sending a pull request <writing-patches>` with a fix.

* search the `scrapy-users`_ list and `Scrapy subreddit`_ to see if it has
  been discussed there, or if you're not sure if what you're seeing is a bug.
  You can also ask in the `#scrapy` IRC channel.

* write **complete, reproducible, specific bug reports**. The smaller the test
  case, the better. Remember that other developers won't have your project to
  reproduce the bug, so please include all relevant files required to reproduce
  it. See for example StackOverflow's guide on creating a
  `Minimal, Complete, and Verifiable example`_ exhibiting the issue.

* the most awesome way to provide a complete reproducible example is to
  send a pull request which adds a failing test case to the
  Scrapy testing suite (see :ref:`submitting-patches`).
  This is helpful even if you don't have an intention to
  fix the issue yourselves.

* include the output of ``scrapy version -v`` so developers working on your bug
  know exactly which version and platform it occurred on, which is often very
  helpful for reproducing it, or knowing if it was already fixed.

.. _Minimal, Complete, and Verifiable example: https://stackoverflow.com/help/mcve

.. _writing-patches:

Writing patches
===============

The better a patch is written, the higher the chances that it'll get accepted and the sooner it will be merged.

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

.. _submitting-patches:

Submitting patches
==================

The best way to submit a patch is to issue a `pull request`_ on GitHub,
optionally creating a new issue first.

Remember to explain what was fixed or the new functionality (what it is, why
it's needed, etc). The more info you include, the easier will be for core
developers to understand and accept your patch.

You can also discuss the new functionality (or bug fix) before creating the
patch, but it's always good to have a patch ready to illustrate your arguments
and show that you have put some additional thought into the subject. A good
starting point is to send a pull request on GitHub. It can be simple enough to
illustrate your idea, and leave documentation/tests for later, after the idea
has been validated and proven useful. Alternatively, you can start a
conversation in the `Scrapy subreddit`_ to discuss your idea first.

Sometimes there is an existing pull request for the problem you'd like to
solve, which is stalled for some reason. Often the pull request is in a
right direction, but changes are requested by Scrapy maintainers, and the
original pull request author hasn't had time to address them.
In this case consider picking up this pull request: open
a new pull request with all commits from the original pull request, as well as
additional changes to address the raised issues. Doing so helps a lot; it is
not considered rude as soon as the original author is acknowledged by keeping
his/her commits.

You can pull an existing pull request to a local branch
by running ``git fetch upstream pull/$PR_NUMBER/head:$BRANCH_NAME_TO_CREATE``
(replace 'upstream' with a remote name for scrapy repository,
``$PR_NUMBER`` with an ID of the pull request, and ``$BRANCH_NAME_TO_CREATE``
with a name of the branch you want to create locally).
See also: https://help.github.com/articles/checking-out-pull-requests-locally/#modifying-an-inactive-pull-request-locally.

When writing GitHub pull requests, try to keep titles short but descriptive.
E.g. For bug #411: "Scrapy hangs if an exception raises in start_requests"
prefer "Fix hanging when exception occurs in start_requests (#411)"
instead of "Fix for #411". Complete titles make it easy to skim through
the issue tracker.

Finally, try to keep aesthetic changes (:pep:`8` compliance, unused imports
removal, etc) in separate commits from functional changes. This will make pull
requests easier to review and more likely to get merged.

Coding style
============

Please follow these coding conventions when writing code for inclusion in
Scrapy:

* Unless otherwise specified, follow :pep:`8`.

* It's OK to use lines longer than 80 chars if it improves the code
  readability.

* Don't put your name in the code you contribute; git provides enough
  metadata to identify author of the code.
  See https://help.github.com/articles/setting-your-username-in-git/ for
  setup instructions.

Documentation policies
======================

* **Don't** use docstrings for documenting classes, or methods which are
  already documented in the official (sphinx) documentation. Alternatively,
  **do** provide a docstring, but make sure sphinx documentation uses
  autodoc_ extension to pull the docstring. For example, the
  :meth:`ItemLoader.add_value` method should be either
  documented only in the sphinx documentation (not as a docstring), or
  it should have a docstring which is pulled to sphinx documentation using
  autodoc_ extension.

* **Do** use docstrings for documenting functions not present in the official
  (sphinx) documentation, such as functions from ``scrapy.utils`` package and
  its sub-modules.

.. _autodoc: http://www.sphinx-doc.org/en/stable/ext/autodoc.html

Tests
=====

Tests are implemented using the `Twisted unit-testing framework`_, running
tests requires `tox`_.

Running tests
-------------

Make sure you have a recent enough `tox`_ installation:

    ``tox --version``

If your version is older than 1.7.0, please update it first:

    ``pip install -U tox``

To run all tests go to the root directory of Scrapy source code and run:

    ``tox``

To run a specific test (say ``tests/test_loader.py``) use:

    ``tox -- tests/test_loader.py``

To see coverage report install `coverage`_ (``pip install coverage``) and run:

    ``coverage report``

see output of ``coverage --help`` for more options like html or xml report.

.. _coverage: https://pypi.python.org/pypi/coverage

Writing tests
-------------

All functionality (including new features and bug fixes) must include a test
case to check that it works as expected, so please include tests for your
patches if you want them to get accepted sooner.

Scrapy uses unit-tests, which are located in the `tests/`_ directory.
Their module name typically resembles the full path of the module they're
testing. For example, the item loaders code is in::

    scrapy.loader

And their unit-tests are in::

    tests/test_loader.py

.. _issue tracker: https://github.com/scrapy/scrapy/issues
.. _scrapy-users: https://groups.google.com/forum/#!forum/scrapy-users
.. _Scrapy subreddit: https://reddit.com/r/scrapy
.. _Twisted unit-testing framework: https://twistedmatrix.com/documents/current/core/development/policy/test-standard.html
.. _AUTHORS: https://github.com/scrapy/scrapy/blob/master/AUTHORS
.. _tests/: https://github.com/scrapy/scrapy/tree/master/tests
.. _open issues: https://github.com/scrapy/scrapy/issues
.. _pull request: https://help.github.com/send-pull-requests/
.. _tox: https://pypi.python.org/pypi/tox
