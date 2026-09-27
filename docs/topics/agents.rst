.. _agents:

===============================
Using Scrapy with coding agents
===============================

If you use coding agents to work with Scrapy projects, we recommend installing
the official `agent plugin`_. To install it, point your agent to the plugin
repository URL (read the plugin documentation for more information)::

    https://github.com/scrapy/scrapy-agent-plugin

This plugin adds a skill that helps agents build and troubleshoot Scrapy
projects, and configures the official `Scrapy MCP server`_, which allows agents
to connect to Scrapy crawls.

.. _using-mcp-server:

Using the MCP server
====================

.. versionadded:: 2.19.0

The `Scrapy MCP server`_ can connect to running local crawls that have the
:class:`~.RemoteControl` extension enabled. Here are some tasks that are
possible thanks to it:

- Checking on the progress of a crawl, by looking at the current values of
  :ref:`stats <topics-stats>` and, when that's not enough, by inspecting core
  objects such as the :ref:`scheduler <topics-scheduler>` directly.

- Investigating why a crawl is slow, doesn't make requests, or makes requests
  without producing items, by looking at its runtime state, settings, and
  source code. It's also easy to see how the runtime state (e.g. the stats or
  the queue state) changes over a set amount of time, by reading it twice in
  the same request with an :func:`asyncio.sleep` call in between.
  See :ref:`optimize-bottleneck` for more ideas about investigating slow
  crawls.

- Studying memory usage and debugging memory leaks, as described in
  :ref:`topics-leaks`.

- Modifying the runtime state, configuration, and even code of a crawl. This is
  fragile and not always possible, but it may save a broken crawl that is
  expensive or impossible to restart without losing data and that cannot be
  fixed in any other way.

.. _agent plugin: https://github.com/scrapy/scrapy-agent-plugin
.. _Scrapy MCP server: https://github.com/scrapy/scrapy-mcp-official
