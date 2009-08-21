.. _api-stability:

============================
Versioning and API Stability
============================

API stability is one of Scrapy major goals. 

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
document the entire API, as we approach the 1.0 release. 

Also, keep in mind that stable doesn't mean complete: stable APIs could grow
new methods or functionality but the existing methods should keep working the
same way.

