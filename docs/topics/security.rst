.. _security:

========
Security
========

Scrapy defaults are optimized for web scraping, not for the security posture
that you might expect from software that handles untrusted input or runs in a
shared or exposed environment. Some common security practices are unnecessary
for many scraping use cases, and a few can even prevent valid ones (for
example, sites that you must scrape may use misconfigured TLS certificates or
serve content over unencrypted protocols).

This page highlights the Scrapy defaults that have security implications, so
that you can make an informed decision about whether to keep them, and explains
how to harden them along with the trade-offs involved.

.. note::

    None of the options below are silver bullets. Which of them make sense
    depends on your threat model: whether the URLs you crawl come from trusted
    sources, whether the machine running Scrapy is exposed to a network you do
    not control, whether the data you handle is sensitive, and so on.

.. _security-untrusted-responses:

Treat responses as untrusted input
==================================

Regardless of any setting, remember that response data comes from servers you
do not control, even when you trust the site you are crawling, as responses may
be tampered with in transit or the server itself may be compromised.

Never pass response data to functions that can execute code or otherwise act on
their input in an unsafe way, such as :func:`eval`, :func:`exec`, or
:func:`pickle.loads`, and be careful when writing response data to paths
derived from the response itself.

.. _security-response-size:

Memory use when parsing responses
=================================

Parsing a response with :ref:`selectors <topics-selectors>` builds an in-memory
tree of the whole response body, which takes several times as much memory as
the body itself. Scrapy parses without the size limits that libxml2 applies by
default, so the size of that tree is bound only by the size of the response, as
controlled by :setting:`DOWNLOAD_MAXSIZE` (default: 1 GiB).

XML entities are left unresolved, so the tree stays proportional to the
response body even for input crafted as an `XML bomb
<https://lxml.de/FAQ.html#is-lxml-vulnerable-to-xml-bombs>`_. A server can still
make a crawler allocate a lot of memory by returning a very large response,
though, so if you know the size of the responses you care about, lower the
limit:

.. code-block:: python

    DOWNLOAD_MAXSIZE = 32 * 1024 * 1024  # 32 MiB

* **Pro:** a server cannot make the crawler allocate more memory than the limit
  allows, whether by returning a large response or by crafting one that is
  expensive to parse.

* **Con:** you can no longer scrape sites that legitimately serve responses
  above the limit, as those responses are dropped.

.. _security-parser-limits:

Parser limits
-------------

The limits that libxml2 applies by default, such as 256 nesting levels and
10 MB per text node, can be restored by overriding
:attr:`~scrapy.http.TextResponse.selector` in a response subclass and swapping
responses in a :ref:`downloader middleware <topics-downloader-middleware>`:

.. code-block:: python

    from functools import cached_property

    from scrapy import Selector
    from scrapy.http import HtmlResponse


    class LimitedHtmlResponse(HtmlResponse):
        @cached_property
        def selector(self):
            return Selector(self, huge_tree=False)


    class LimitedParsingMiddleware:
        def process_response(self, request, response, spider):
            if isinstance(response, HtmlResponse):
                return response.replace(cls=LimitedHtmlResponse)
            return response

Do the same with :class:`~scrapy.http.XmlResponse` if you also parse XML.

These limits apply per node, so :setting:`DOWNLOAD_MAXSIZE` remains your bound
on total memory: a response made of many small elements is parsed in full and
uses as much memory either way.

* **Pro:** deeply nested responses, and responses with very large individual
  nodes, become cheaper to parse.

* **Con:** parsing stops at those limits without raising, so a legitimate page
  that exceeds them yields incomplete data and no error.

TLS connections
===============

.. _security-certificate-verification:

Certificate verification
------------------------

By default Scrapy does **not** verify the TLS certificate of HTTPS servers, as
controlled by the :setting:`DOWNLOAD_VERIFY_CERTIFICATES` setting (default:
``False``).

This default favors reach over security: many sites that are otherwise fine to
scrape have expired, self-signed, or otherwise invalid certificates, and
verifying certificates would make requests to them fail.

If the integrity of the connection matters to you (for example, to detect
man-in-the-middle attacks), set:

.. code-block:: python

    DOWNLOAD_VERIFY_CERTIFICATES = True

* **Pro:** requests to servers with invalid or untrusted certificates fail
  instead of silently succeeding, protecting you from some man-in-the-middle
  attacks.

* **Con:** you can no longer scrape sites with misconfigured certificates
  without re-disabling verification for them.

.. _security-tls-protocols-ciphers:

Protocol versions and ciphers
-----------------------------

You can restrict the TLS protocol versions that Scrapy accepts through the
:setting:`DOWNLOAD_TLS_MIN_VERSION` and :setting:`DOWNLOAD_TLS_MAX_VERSION`
settings, e.g. to reject obsolete protocol versions.

By default Scrapy uses the OpenSSL ``DEFAULT`` cipher list
(:setting:`DOWNLOADER_CLIENT_TLS_CIPHERS`), which favors compatibility and still
allows some older, weaker ciphers. Set it to ``None`` to instead use the curated
cipher list of the underlying TLS implementation (Twisted), which excludes weak
ciphers:

.. code-block:: python

    DOWNLOADER_CLIENT_TLS_CIPHERS = None

* **Pro:** connections that would negotiate a weak cipher fail instead of
  succeeding.

* **Con:** you can no longer connect to servers that only support the excluded
  ciphers.

.. _security-unencrypted-protocols:

Unencrypted protocols
=====================

By default Scrapy enables download handlers for unencrypted protocols, namely
``http://`` and ``ftp://`` (see :setting:`DOWNLOAD_HANDLERS_BASE`). Data sent
and received over these protocols, including any credentials, travels in plain
text and can be read or modified by anyone on the network path.

If you only crawl over encrypted protocols, you can disable the unencrypted
ones so that no request can accidentally be sent unencrypted:

.. code-block:: python

    DOWNLOAD_HANDLERS = {
        "http": None,
        "ftp": None,
    }

* **Pro:** a misconfigured or maliciously-redirected request cannot leak data
  over an unencrypted connection, as such requests fail instead.

* **Con:** you can no longer crawl resources that are only available over those
  protocols.

Note that disabling the ``http`` handler also prevents plain-HTTP requests that
result from following an ``http://`` redirect or link, which is often the point
of disabling it.

.. _security-local-resources:

Local and non-network resources
===============================

By default Scrapy enables download handlers for the ``file://`` and ``data:``
schemes (see :setting:`DOWNLOAD_HANDLERS_BASE`). The ``file://`` handler reads
arbitrary files from the local filesystem, limited only by the permissions of
the process running Scrapy.

This is convenient (for example, to parse a local HTML file), but it is a risk
if any of the URLs you schedule come from an untrusted source: a crafted
``file:///etc/passwd`` URL could read local files.

If you do not need them, disable these handlers:

.. code-block:: python

    DOWNLOAD_HANDLERS = {
        "file": None,
        "data": None,
    }

* **Pro:** crawled URLs cannot be used to read local files or inline data.

* **Con:** you can no longer fetch ``file://`` or ``data:`` URLs.

More generally, if you crawl URLs from untrusted sources, consider validating
their schemes (and, where applicable, their hosts) before scheduling requests,
to avoid server-side request forgery (SSRF) and similar issues.

.. _security-remote-control:

Remote control server
=====================

Scrapy enables the remote control HTTP server
(:class:`scrapy.extensions.remote_control.RemoteControl`) by default
(:setting:`REMOTE_CONTROL_ENABLED`). Its purpose is to run arbitrary code
inside the Scrapy process, so anyone who can connect to it can do that.

The server listens on a random localhost port and requires a token for
authentication. This token is stored in a job file (see
:setting:`REMOTE_CONTROL_JOBS_DIR` for the location of these files), so you
should protect these files from unauthorized access. On Linux and macOS systems
Scrapy sets file system permissions for job files and the directory containing
them to be accessible only by the owner.

.. note::

    The server doesn't use HTTPS so it's possible to sniff the traffic or
    tamper with it, but it requires the attacker to get access to the loopback
    traffic.

If you do not use this feature, disable it entirely:

.. code-block:: python

    REMOTE_CONTROL_ENABLED = False

* **Pro:** removes a local code-execution surface and one less listening port.

* **Con:** you can no longer inspect and control a running crawler through it.

.. _security-telnet:

Telnet console
==============

Scrapy enables the :ref:`telnet console <topics-telnetconsole>` by default
(:setting:`TELNETCONSOLE_ENABLED`). The telnet console is a Python shell
running inside the Scrapy process, so anyone who can connect to it can run
arbitrary code in that process.

By default the console binds to ``127.0.0.1`` (:setting:`TELNETCONSOLE_HOST`)
and is protected by a username (:setting:`TELNETCONSOLE_USERNAME`, default
``scrapy``) and an automatically generated password
(:setting:`TELNETCONSOLE_PASSWORD`), so it is only reachable from the local
machine.

.. warning::

    Telnet does not provide any transport-layer security, so the
    username/password authentication does not protect the credentials or the
    session from anyone able to observe the traffic. Never expose the telnet
    console over an untrusted network by changing :setting:`TELNETCONSOLE_HOST`
    to a non-local address.

If you do not use the telnet console, disable it entirely:

.. code-block:: python

    TELNETCONSOLE_ENABLED = False

* **Pro:** removes a local code-execution surface and one less listening port.

* **Con:** you can no longer :ref:`inspect and control a running crawler
  <topics-telnetconsole>` through it.

.. _security-credential-leakage:

Credential leakage across domains
=================================

Some Scrapy features attach credentials or other sensitive headers to requests,
and a crawl that spans multiple domains can leak them to unintended hosts:

* HTTP authentication credentials set through
  :class:`~scrapy.downloadermiddlewares.httpauth.HttpAuthMiddleware` are only
  sent to the domain set in :setting:`HTTPAUTH_DOMAIN`. Leave this set to the
  intended domain rather than ``None`` so that credentials are not sent to
  every domain you crawl.

* The ``Referer`` header may disclose the URLs you crawl to other sites. The
  default :setting:`REFERRER_POLICY` already avoids sending the referrer from
  HTTPS to HTTP, but you can tighten it further (for example, to
  ``same-origin`` or ``no-referrer``) if needed.
