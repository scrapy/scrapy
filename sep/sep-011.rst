=======  ================================
SEP      11
Title    Process models for Scrapy
Created  2009-11-16
Status   Partially implemented - see #168
=======  ================================

==================================
SEP-011: Process models for Scrapy
==================================

There is an interest of supporting different process models for Scrapy, mainly
to help prevent memory leaks which affect running all spiders in the same
process.

By running each spider on a separate process (or pool of processes) we'll be
able to "recycle" process when they exceed a maximum amount of memory.

Supported process models
========================

The user could choose between different process models:

1. in process (only method supported so far)
2. pooled processes (a predefined pool of N processes, which could run more than one spider each)
3. separate processes (one process per spider)

Using different processes would increase reliability at the cost of performance.

Another ideas to consider
=========================

- configuring pipeline process models - so that we can have a process exclusive
  for running pipelines
- support writing spidersr in different languages when we don't use an in
  process model
