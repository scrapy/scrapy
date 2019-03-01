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
  and things that possibly break backward compatibility, although we strive to
  keep theses cases at a minimum.
* *C* is the bugfix release number.

For example:

*   Upgrading from ``1.0.0`` to ``1.0.1`` will not require code changes unless
    deemed necessary; for example, for security reasons.

*   Upgrading from ``1.0.0`` to ``1.1.0`` may require code changes.

*   Upgrading from ``1.0.0`` to ``2.0.0`` will require code changes.

Backward-incompatibilities are explicitly mentioned in the
:ref:`release notes <news>` and in the :ref:`deprecation list
<current-deprecations>`, and may require special attention before upgrading.


API Stability
=============

Names that start with a single dash (``_``) are private and you should never
rely on them being stable. They may be changed or removed in any version, even
in bugfix releases, and this will not be covered in the :ref:`release notes
<news>` or in the :ref:`deprecation list <current-deprecations>`.

Also, keep in mind that stable doesn't mean complete: stable APIs could grow
new methods or functionality but the existing methods should keep working the
same way.
