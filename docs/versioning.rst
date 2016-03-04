.. _versioning:

============================
Versioning and API Stability
============================

Versioning
==========

Scrapy uses the `odd-numbered versions for development releases`_.

There are 3 numbers in a Scrapy version: *A.B.C*

* *A* is the major version. This will rarely change and will signify very
  large changes.
* *B* is the release number. This will include many changes including features
  and things that possibly break backwards compatibility. Even Bs will be
  stable branches, and odd Bs will be development.
* *C* is the bugfix release number.

For example:

* *0.14.1* is the first bugfix release of the *0.14* series (safe to use in
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

