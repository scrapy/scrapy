.. _misc-api-stability:

============================
Versioning and API Stability
============================

API stability is one of Scrapy major goals. We're currently working on
documenting and stabilizing the main parts of Scrapy towards the first official
release (version |version|).

Versioning
==========

Each Scrapy release consists of three version numbers:

 * major - big, backwards-incompatible changes
 * minor - new features and backwards-compatible changes
 * micro - bug fixes only

Sometimes the micro version can be omitted, for brevity, when it's not
relevant.

API Stability
=============

Methods or functions that start with a single dash (``_``) are private and
should never be relied as stable. Besides those, the plan is to stabilize and
document the entire API, as we approach the 1.0 release. In the meantime,
you'll find here a list of the APIs that we consider already stable.

Also, keep in mind that stable doesn't mean complete: stable APIs could grow
new methods or functionality but the existing methods should keep working the
same way.

