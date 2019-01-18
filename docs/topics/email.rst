.. currentmodule:: scrapy.mail

.. _topics-email:

==============
Sending e-mail
==============

Although Python makes sending e-mails relatively easy via the :mod:`smtplib`
module, Scrapy provides its own facility for sending e-mails which is very
easy to use and it's implemented using `Twisted non-blocking IO`_, to avoid
interfering with the non-blocking IO of the crawler. It also provides a
simple API for sending attachments and it's very easy to configure, with a few
:ref:`settings <topics-email-settings>`.

.. _Twisted non-blocking IO: https://twistedmatrix.com/documents/current/core/howto/defer-intro.html

Quick example
=============

There are two ways to instantiate the mail sender. You can instantiate it using
the standard constructor::

    from scrapy.mail import MailSender
    mailer = MailSender()

Or you can instantiate it passing a Scrapy settings object, which will respect
the :ref:`settings <topics-email-settings>`::

    mailer = MailSender.from_settings(settings)

And here is how to use it to send an e-mail (without attachments)::

    mailer.send(to=["someone@example.com"], subject="Some subject", body="Some body", cc=["another@example.com"])

.. _topics-email-settings:

Mail settings
=============

These settings define the default constructor values of the :class:`MailSender`
class, and can be used to configure e-mail notifications in your project without
writing any code (for those extensions and code that uses :class:`MailSender`).

.. setting:: MAIL_FROM

MAIL_FROM
---------

Default: ``'scrapy@localhost'``

Sender email to use (``From:`` header) for sending emails.

.. setting:: MAIL_HOST

MAIL_HOST
---------

Default: ``'localhost'``

SMTP host to use for sending emails.

.. setting:: MAIL_PORT

MAIL_PORT
---------

Default: ``25``

SMTP port to use for sending emails.

.. setting:: MAIL_USER

MAIL_USER
---------

Default: ``None``

User to use for SMTP authentication. If disabled no SMTP authentication will be
performed.

.. setting:: MAIL_PASS

MAIL_PASS
---------

Default: ``None``

Password to use for SMTP authentication, along with :setting:`MAIL_USER`.

.. setting:: MAIL_TLS

MAIL_TLS
--------

Default: ``False``

Enforce using STARTTLS. STARTTLS is a way to take an existing insecure connection, and upgrade it to a secure connection using SSL/TLS.

.. setting:: MAIL_SSL

MAIL_SSL
--------

Default: ``False``

Enforce connecting using an SSL encrypted connection
