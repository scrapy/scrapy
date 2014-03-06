=======  ===========================================
SEP      10
Title    REST API
Author   Pablo Hoffman
Created  2009-11-16
Status   Obsolete (JSON-RPC API implemented instead)
=======  ===========================================

=================
SEP-010: REST API
=================

This SEP proposes a JSON REST API for controlling Scrapy in server-mode, which
is launched with: ``scrapy-ctl.py start``

Operations
==========

Get list of available spiders
-----------------------------

``GET /spiders/all``

Get list of closed spiders
--------------------------

``GET /spiders/closed``

Get list of scheduled spiders
-----------------------------

``GET /spiders/scheduled``

.. note:: contains closed

Get list of running spiders
---------------------------

``GET /spiders/opened``

- returns list of dicts containing spider ``id`` and ``domain_name``

Schedule spider
---------------

``POST /spiders``

- args: ``schedule=example.com``

Close spider
------------

``POST /spider/1238/close``

Get global stats
----------------

``GET /stats``

.. note:: spider-specific not included

Get spider-specific stats
-------------------------

``GET /spider/1238/stats/``

Get engine status
-----------------

``GET /engine/status``
