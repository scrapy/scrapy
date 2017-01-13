===========================================
Service Identity Verification for pyOpenSSL
===========================================

.. image:: https://travis-ci.org/pyca/service_identity.svg?branch=master
  :target: https://travis-ci.org/pyca/service_identity

.. image:: https://codecov.io/github/pyca/service_identity/coverage.svg?branch=master
  :target: https://codecov.io/github/pyca/service_identity

.. image:: https://www.irccloud.com/invite-svg?channel=%23cryptography-dev&amp;hostname=irc.freenode.net&amp;port=6697&amp;ssl=1
    :target: https://www.irccloud.com/invite?channel=%23cryptography-dev&amp;hostname=irc.freenode.net&amp;port=6697&amp;ssl=1

.. begin

**TL;DR**: Use this package if you use pyOpenSSL_ and don’t want to be MITM_\ ed.

``service_identity`` aspires to give you all the tools you need for verifying whether a certificate is valid for the intended purposes.

In the simplest case, this means *host name verification*.
However, ``service_identity`` implements `RFC 6125`_ fully and plans to add other relevant RFCs too.

``service_identity``\ ’s documentation lives at `Read the Docs <https://service-identity.readthedocs.org/>`_, the code on `GitHub <https://github.com/pyca/service_identity>`_.


.. _Twisted: https://twistedmatrix.com/
.. _pyOpenSSL: https://pypi.python.org/pypi/pyOpenSSL/
.. _MITM: https://en.wikipedia.org/wiki/Man-in-the-middle_attack
.. _`RFC 6125`: http://www.rfc-editor.org/info/rfc6125


Release Information
===================

16.0.0 (2016-02-18)
-------------------

Backward-incompatible changes:
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Python 3.3 and 2.6 aren't supported anymore.
  They may work by chance but any effort to keep them working has ceased.

  The last Python 2.6 release was on October 29, 2013 and isn't supported by the CPython core team anymore.
  Major Python packages like Django and Twisted dropped Python 2.6 a while ago already.

  Python 3.3 never had a significant user base and wasn't part of any distribution's LTS release.
- pyOpenSSL versions older than 0.14 are not tested anymore.
  They don't even build with recent OpenSSL versions.

Changes:
^^^^^^^^

- Officially support Python 3.5.
- ``service_identity.SubjectAltNameWarning`` is now raised if the server certicate lacks a proper ``SubjectAltName``.
  [`#9 <https://github.com/pyca/service_identity/issues/9>`_]
- Add a ``__str__`` method to ``VerificationError``.
- Port from ``characteristic`` to its spiritual successor `attrs <https://attrs.readthedocs.org/>`_.

`Full changelog <https://service-identity.readthedocs.org/en/stable/changelog.html>`_.

Authors
=======

``service_identity`` is written and maintained by `Hynek Schlawack <https://hynek.me/>`_.

The development is kindly supported by `Variomedia AG <https://www.variomedia.de/>`_.

Other contributors can be found in `GitHub's overview <https://github.com/pyca/service_identity/graphs/contributors>`_.


