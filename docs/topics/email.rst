.. _topics-email:

==============
Sending e-mail
==============

.. module:: scrapy.mail
   :synopsis: Email sending facility

Although Python makes sending e-mails relatively easy via the :mod:`smtplib`
library, Scrapy provides its own facility for sending e-mails which is very
easy to use and it's implemented using :doc:`Twisted non-blocking IO
<twisted:core/howto/defer-intro>`, to avoid interfering with the non-blocking
IO of the crawler. It also provides a simple API for sending attachments and
it's very easy to configure, with a few :ref:`settings
<topics-email-settings>`.

Quick example
=============

There are two ways to instantiate the mail sender. You can instantiate it using
the standard ``__init__`` method::

    from scrapy.mail import MailSender
    mailer = MailSender()

Or you can instantiate it passing a Scrapy settings object, which will respect
the :ref:`settings <topics-email-settings>`::

    mailer = MailSender.from_settings(settings)

And here is how to use it to send an e-mail (without attachments)::

    mailer.send(to=["someone@example.com"], subject="Some subject", body="Some body", cc=["another@example.com"])

MailSender class reference
==========================

MailSender is the preferred class to use for sending emails from Scrapy, as it
uses :doc:`Twisted non-blocking IO <twisted:core/howto/defer-intro>`, like the
rest of the framework.

.. class:: MailSender(smtphost=None, mailfrom=None, smtpuser=None, smtppass=None, smtpport=None)

    :param smtphost: the SMTP host to use for sending the emails. If omitted, the
      :setting:`MAIL_HOST` setting will be used.
    :type smtphost: str

    :param mailfrom: the address used to send emails (in the ``From:`` header).
      If omitted, the :setting:`MAIL_FROM` setting will be used.
    :type mailfrom: str

    :param smtpuser: the SMTP user. If omitted, the :setting:`MAIL_USER`
      setting will be used. If not given, no SMTP authentication will be
      performed.
    :type smtphost: str or bytes

    :param smtppass: the SMTP pass for authentication.
    :type smtppass: str or bytes

    :param smtpport: the SMTP port to connect to
    :type smtpport: int

    :param smtptls: enforce using SMTP STARTTLS
    :type smtptls: boolean

    :param smtpssl: enforce using a secure SSL connection
    :type smtpssl: boolean

    .. classmethod:: from_settings(settings)

        Instantiate using a Scrapy settings object, which will respect
        :ref:`these Scrapy settings <topics-email-settings>`.

        :param settings: the e-mail recipients
        :type settings: :class:`scrapy.settings.Settings` object

    .. method:: send(to, subject, body, cc=None, attachs=(), mimetype='text/plain', charset=None)

        Send email to the given recipients.

        :param to: the e-mail recipients
        :type to: str or list of str

        :param subject: the subject of the e-mail
        :type subject: str

        :param cc: the e-mails to CC
        :type cc: str or list of str

        :param body: the e-mail body
        :type body: str

        :param attachs: an iterable of tuples ``(attach_name, mimetype,
          file_object)`` where  ``attach_name`` is a string with the name that will
          appear on the e-mail's attachment, ``mimetype`` is the mimetype of the
          attachment and ``file_object`` is a readable file object with the
          contents of the attachment
        :type attachs: iterable

        :param mimetype: the MIME type of the e-mail
        :type mimetype: str

        :param charset: the character encoding to use for the e-mail contents
        :type charset: str


.. _topics-email-settings:

Mail settings
=============

These settings define the default ``__init__`` method values of the :class:`MailSender`
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
