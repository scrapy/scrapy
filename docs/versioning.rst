.. _versioning:

============================
Versioning and API Stability
============================

Versioning
==========

Scrapy uses the `odd-numbered versions for development releases`_.

There are 4 numbers in a Scrapy version: *A.B.C.D*

* *A* is the major version. This will rarely change and will signify very
  large changes. So far, only zero is available for *A*
* *B* is the release number. This will include many changes including features
  and things that possible break backwards compatibility. Even Bs will be
  stable branches, and odd Bs will be development.
* *C* is the bugfix release number, but it has been recently deprecated of
  favor of using the revision number (*D*)
* *D* is an incremental number (aka. revision) based on the number of commits
  in the git repo where the release was taken

For example:

* *0.12.0.2542* is the stable release *12* at revision *2542* (safe to use in
  production)
* *0.13.0.2691* is the development release *13* at revision *2691* (use with
  care in production)

API Stability
=============

API stability is one of Scrapy major goals for the *1.0* release, which doesn't
have a due date scheduled yet.

Methods or functions that start with a single dash (``_``) are private and
should never be relied as stable. Besides those, the plan is to stabilize and
document the entire API, as we approach the 1.0 release. 

Also, keep in mind that stable doesn't mean complete: stable APIs could grow
new methods or functionality but the existing methods should keep working the
same way.


.. _odd-numbered versions for development releases: http://en.wikipedia.org/wiki/Software_versioning#Odd-numbered_versions_for_development_releases

