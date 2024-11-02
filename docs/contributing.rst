.. _topics-contributing:

======================
Contributing to Scrapy
======================

.. important::

    Double check that you are reading the most recent version of this document at
    https://docs.scrapy.org/en/master/contributing.html

There are many ways to contribute to Scrapy. Here are some of them:

* Report bugs and request features in the `issue tracker`_, trying to follow
  the guidelines detailed in `Reporting bugs`_ below.

* Submit patches for new functionalities and/or bug fixes. Please read
  :ref:`writing-patches` and `Submitting patches`_ below for details on how to
  write and submit a patch.

* Blog about Scrapy. Tell the world how you're using Scrapy. This will help
  newcomers with more examples and will help the Scrapy project to increase its
  visibility.

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

* if you have a general question about Scrapy usage, please ask it at
  `Stack Overflow <https://stackoverflow.com/questions/tagged/scrapy>`__
  (use "scrapy" tag).

* check the `open issues`_ to see if the issue has already been reported. If it
  has, don't dismiss the report, but check the ticket history and comments. If
  you have additional useful information, please leave a comment, or consider
  :ref:`sending a pull request <writing-patches>` with a fix.

* search the `scrapy-users`_ list and `Scrapy subreddit`_ to see if it has
  been discussed there, or if you're not sure if what you're seeing is a bug.
  You can also ask in the ``#scrapy`` IRC channel.

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

Scrapy has a list of `good first issues`_ and `help wanted issues`_ that you
can work on. These issues are a great way to get started with contributing to
Scrapy. If you're new to the codebase, you may want to focus on documentation
or testing-related issues, as they are always useful and can help you get
more familiar with the project. You can also check Scrapy's `test coverage`_
to see which areas may benefit from more tests.

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

* if you're adding a private API, please add a regular expression to the
  ``coverage_ignore_pyobjects`` variable of ``docs/conf.py`` to exclude the new
  private API from documentation coverage checks.

  To see if your private API is skipped properly, generate a documentation
  coverage report as follows::

      tox -e docs-coverage

* if you are removing deprecated code, first make sure that at least 1 year
  (12 months) has passed since the release that introduced the deprecation.
  See :ref:`deprecation-policy`.


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
not considered rude as long as the original author is acknowledged by keeping
his/her commits.

You can pull an existing pull request to a local branch
by running ``git fetch upstream pull/$PR_NUMBER/head:$BRANCH_NAME_TO_CREATE``
(replace 'upstream' with a remote name for scrapy repository,
``$PR_NUMBER`` with an ID of the pull request, and ``$BRANCH_NAME_TO_CREATE``
with a name of the branch you want to create locally).
See also: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/checking-out-pull-requests-locally#modifying-an-inactive-pull-request-locally.

When writing GitHub pull requests, try to keep titles short but descriptive.
E.g. For bug #411: "Scrapy hangs if an exception raises in start_requests"
prefer "Fix hanging when exception occurs in start_requests (#411)"
instead of "Fix for #411". Complete titles make it easy to skim through
the issue tracker.

Finally, try to keep aesthetic changes (:pep:`8` compliance, unused imports
removal, etc) in separate commits from functional changes. This will make pull
requests easier to review and more likely to get merged.


.. _coding-style:

Coding style
============

Please follow these coding conventions when writing code for inclusion in
Scrapy:

* We use `black <https://black.readthedocs.io/en/stable/>`_ for code formatting.
  There is a hook in the pre-commit config
  that will automatically format your code before every commit. You can also
  run black manually with ``tox -e pre-commit``.

* Don't put your name in the code you contribute; git provides enough
  metadata to identify author of the code.
  See https://docs.github.com/en/get-started/getting-started-with-git/setting-your-username-in-git
  for setup instructions.

.. _scrapy-pre-commit:

Pre-commit
==========

We use `pre-commit`_ to automatically address simple code issues before every
commit.

.. _pre-commit: https://pre-commit.com/

After your create a local clone of your fork of the Scrapy repository:

#.  `Install pre-commit <https://pre-commit.com/#installation>`_.

#.  On the root of your local clone of the Scrapy repository, run the following
    command:

    .. code-block:: bash

       pre-commit install

Now pre-commit will check your changes every time you create a Git commit. Upon
finding issues, pre-commit aborts your commit, and either fixes those issues
automatically, or only reports them to you. If it fixes those issues
automatically, creating your commit again should succeed. Otherwise, you may
need to address the corresponding issues manually first.

.. _documentation-policies:

Documentation policies
======================

For reference documentation of API members (classes, methods, etc.) use
docstrings and make sure that the Sphinx documentation uses the
:mod:`~sphinx.ext.autodoc` extension to pull the docstrings. API reference
documentation should follow docstring conventions (`PEP 257`_) and be
IDE-friendly: short, to the point, and it may provide short examples.

Other types of documentation, such as tutorials or topics, should be covered in
files within the ``docs/`` directory. This includes documentation that is
specific to an API member, but goes beyond API reference documentation.

In any case, if something is covered in a docstring, use the
:mod:`~sphinx.ext.autodoc` extension to pull the docstring into the
documentation instead of duplicating the docstring in files within the
``docs/`` directory.

Documentation updates that cover new or modified features must use Sphinx’s
:rst:dir:`versionadded` and :rst:dir:`versionchanged` directives. Use
``VERSION`` as version, we will replace it with the actual version right before
the corresponding release. When we release a new major or minor version of
Scrapy, we remove these directives if they are older than 3 years.

Documentation about deprecated features must be removed as those features are
deprecated, so that new readers do not run into it. New deprecations and
deprecation removals are documented in the :ref:`release notes <news>`.


Tests
=====

Tests are implemented using the :doc:`Twisted unit-testing framework
<twisted:development/test-standard>`. Running tests requires
:doc:`tox <tox:index>`.

.. _running-tests:

Running tests
-------------

To run all tests::

    tox

To run a specific test (say ``tests/test_loader.py``) use:

    ``tox -- tests/test_loader.py``

To run the tests on a specific :doc:`tox <tox:index>` environment, use
``-e <name>`` with an environment name from ``tox.ini``. For example, to run
the tests with Python 3.10 use::

    tox -e py310

You can also specify a comma-separated list of environments, and use :ref:`tox’s
parallel mode <tox:parallel_mode>` to run the tests on multiple environments in
parallel::

    tox -e py39,py310 -p auto

To pass command-line options to :doc:`pytest <pytest:index>`, add them after
``--`` in your call to :doc:`tox <tox:index>`. Using ``--`` overrides the
default positional arguments defined in ``tox.ini``, so you must include those
default positional arguments (``scrapy tests``) after ``--`` as well::

    tox -- scrapy tests -x  # stop after first failure

You can also use the `pytest-xdist`_ plugin. For example, to run all tests on
the Python 3.10 :doc:`tox <tox:index>` environment using all your CPU cores::

    tox -e py310 -- scrapy tests -n auto

To see coverage report install :doc:`coverage <coverage:index>`
(``pip install coverage``) and run:

    ``coverage report``

see output of ``coverage --help`` for more options like html or xml report.

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
.. _AUTHORS: https://github.com/scrapy/scrapy/blob/master/AUTHORS
.. _tests/: https://github.com/scrapy/scrapy/tree/master/tests
.. _open issues: https://github.com/scrapy/scrapy/issues
.. _PEP 257: https://peps.python.org/pep-0257/
.. _pull request: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request
.. _pytest-xdist: https://github.com/pytest-dev/pytest-xdist
.. _good first issues: https://github.com/scrapy/scrapy/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22
.. _help wanted issues: https://github.com/scrapy/scrapy/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22
.. _test coverage: https://app.codecov.io/gh/scrapy/scrapy
