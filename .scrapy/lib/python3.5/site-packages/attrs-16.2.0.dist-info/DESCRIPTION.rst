=====================================
attrs: Attributes Without Boilerplate
=====================================

.. image:: https://readthedocs.org/projects/attrs/badge/?version=stable
   :target: http://attrs.readthedocs.io/en/stable/?badge=stable
   :alt: Documentation Status

.. image:: https://travis-ci.org/hynek/attrs.svg?branch=master
   :target: https://travis-ci.org/hynek/attrs
   :alt: CI status

.. image:: https://codecov.io/github/hynek/attrs/branch/master/graph/badge.svg
  :target: https://codecov.io/github/hynek/attrs
  :alt: Test Coverage

.. teaser-begin

``attrs`` is the Python package that will bring back the **joy** of **writing classes** by relieving you from the drudgery of implementing object protocols (aka `dunder <http://nedbatchelder.com/blog/200605/dunder.html>`_ methods).

Its main goal is to help you to write **concise** and **correct** software without slowing down your code.

.. -spiel-end-

For that, it gives you a class decorator and a way to declaratively define the attributes on that class:

.. -code-begin-

.. code-block:: pycon

   >>> import attr
   >>> @attr.s
   ... class C(object):
   ...     x = attr.ib(default=42)
   ...     y = attr.ib(default=attr.Factory(list))
   ...
   ...     def hard_math(self, z):
   ...         return self.x * self.y * z
   >>> i = C(x=1, y=2)
   >>> i
   C(x=1, y=2)
   >>> i.hard_math(3)
   6
   >>> i == C(1, 2)
   True
   >>> i != C(2, 1)
   True
   >>> attr.asdict(i)
   {'y': 2, 'x': 1}
   >>> C()
   C(x=42, y=[])
   >>> C2 = attr.make_class("C2", ["a", "b"])
   >>> C2("foo", "bar")
   C2(a='foo', b='bar')


After *declaring* your attributes ``attrs`` gives you:

- a concise and explicit overview of the class's attributes,
- a nice human-readable ``__repr__``,
- a complete set of comparison methods,
- an initializer,
- and much more,

*without* writing dull boilerplate code again and again and *without* runtime performance penalties.

This gives you the power to use actual classes with actual types in your code instead of confusing ``tuple``\ s or confusingly behaving ``namedtuple``\ s.
Which in turn encourages you to write *small classes* that do `one thing well <https://www.destroyallsoftware.com/talks/boundaries>`_.
Never again violate the `single responsibility principle <https://en.wikipedia.org/wiki/Single_responsibility_principle>`_ just because implementing ``__init__`` et al is a painful drag.


.. -testimonials-

Testimonials
============

  I’m looking forward to is being able to program in Python-with-attrs everywhere.
  It exerts a subtle, but positive, design influence in all the codebases I’ve see it used in.

  -- Glyph Lefkowitz, inventor of Twisted and Software Developer at Rackspace in `The One Python Library Everyone Needs <https://glyph.twistedmatrix.com/2016/08/attrs.html>`_


  I'm increasingly digging your attr.ocity. Good job!

  -- Łukasz Langa, prolific CPython core developer and Production Engineer at Facebook

.. -end-

.. -project-information-

Project Information
===================

``attrs`` is released under the `MIT <http://choosealicense.com/licenses/mit/>`_ license,
its documentation lives at `Read the Docs <https://attrs.readthedocs.io/>`_,
the code on `GitHub <https://github.com/hynek/attrs>`_,
and the latest release on `PyPI <https://pypi.org/project/attrs/>`_.
It’s rigorously tested on Python 2.7, 3.4+, and PyPy.


Release Information
===================

16.2.0 (2016-09-17)
-------------------

Changes:
^^^^^^^^

- Add ``attr.astuple()`` that -- similarly to ``attr.asdict()`` -- returns the instance as a tuple.
  `#77 <https://github.com/hynek/attrs/issues/77>`_
- Converts now work with frozen classes.
  `#76 <https://github.com/hynek/attrs/issues/76>`_
- Instantiation of ``attrs`` classes with converters is now significantly faster.
  `#80 <https://github.com/hynek/attrs/pull/80>`_
- Pickling now works with ``__slots__`` classes.
  `#81 <https://github.com/hynek/attrs/issues/81>`_
- ``attr.assoc()`` now works with ``__slots__`` classes.
  `#84 <https://github.com/hynek/attrs/issues/84>`_
- The tuple returned by ``attr.fields()`` now also allows to access the ``Attribute`` instances by name.
  Yes, we've subclassed ``tuple`` so you don't have to!
  Therefore ``attr.fields(C).x`` is equivalent to the deprecated ``C.x`` and works with ``__slots__`` classes.
  `#88 <https://github.com/hynek/attrs/issues/88>`_

`Full changelog <https://attrs.readthedocs.io/en/stable/changelog.html>`_.

Credits
=======

``attrs`` is written and maintained by `Hynek Schlawack <https://hynek.me/>`_.

The development is kindly supported by `Variomedia AG <https://www.variomedia.de/>`_.

A full list of contributors can be found in `GitHub's overview <https://github.com/hynek/attrs/graphs/contributors>`_.

It’s the spiritual successor of `characteristic <https://characteristic.readthedocs.io/>`_ and aspires to fix some of it clunkiness and unfortunate decisions.
Both were inspired by Twisted’s `FancyEqMixin <https://twistedmatrix.com/documents/current/api/twisted.python.util.FancyEqMixin.html>`_ but both are implemented using class decorators because `sub-classing is bad for you <https://www.youtube.com/watch?v=3MNVP9-hglc>`_, m’kay?


