.. _versioning:

============================
Versioning and API Stability
============================

Versioning
==========

There are 3 numbers in a Scrapy version: *A.B.C*

* *A* is the major version. This will rarely change and will signify very
  large changes.
* *B* is the release number. This will include many changes including features
  and things that possibly break backwards compatibility, although we strive to
  keep theses cases at a minimum.
* *C* is the bugfix release number.

Backward-incompatibilities are explicitly mentioned in the :ref:`release notes <news>`,
and may require special attention before upgrading.

Development releases do not follow 3-numbers version and are generally
released as ``dev`` suffixed versions, e.g. ``1.3dev``.

.. note::
    With Scrapy 0.* series, Scrapy used `odd-numbered versions for development releases`_.
    This is not the case anymore from Scrapy 1.0 onwards.

    Starting with Scrapy 1.0, all releases should be considered production-ready.

For example:

* *1.1.1* is the first bugfix release of the *1.1* series (safe to use in
  production)


API Stability
=============

API stability was one of the major goals for the *1.0* release.

Methods or functions that start with a single dash (``_``) are private and
should never be relied as stable.

Also, keep in mind that stable doesn't mean complete: stable APIs could grow
new methods or functionality but the existing methods should keep working the
same way.


.. _odd-numbered versions for development releases: https://en.wikipedia.org/wiki/Software_versioning#Odd-numbered_versions_for_development_releases

