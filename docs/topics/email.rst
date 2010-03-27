.. _topics-email:

=============
Sending email
=============

.. module:: scrapy.mail
   :synopsis: Email sending facility

Although Python makes sending e-mail relatively easy via the `smtplib`_
library, Scrapy provides its own facility for sending emails which is very easy
to use and it's implemented using `Twisted non-blocking IO`_, to avoid
interfering with the non-blocking IO of the crawler.

It's also very easy to configure by just configuring a few settings.

.. _smtplib: http://docs.python.org/library/smtplib.html
.. _Twisted non-blocking IO: http://twistedmatrix.com/projects/core/documentation/howto/async.html

It also has built-in support for sending attachments.

Quick example
=============

Here's a quick example of how to send an email (without attachments)::

    from scrapy.mail import MailSender

    mailer = MailSender()
    mailer.send(to=["someone@example.com"], subject="Some subject", body="Some body", cc=["another@example.com"])

MailSender class reference
==========================

MailSender is the preferred class to use for sending emails from Scrapy, as it
uses `Twisted non-blocking IO`_, like the rest of the framework. 

.. class:: MailSender(smtphost, mailfrom)

    :param smtphost: the SMTP host to use for sending the emails. If omitted,
      :setting:`MAIL_HOST` setting will be used.
    :type smtphost: str

    :param mailfrom: the address used to send emails (in the ``From:`` header).
      If omitted, :setting:`MAIL_FROM` setting will be used.
    :type mailfrom: str

    .. method:: send(to, subject, body, cc=None, attachs=())

        Send email to the given recipients

        :param to: the email recipients
        :type to: list

        :param subject: the subject of the email
        :type subject: str

        :param cc: the emails to CC
        :type cc: list

        :param body: the email body
        :type body: str

        :param attachs: an iterable of tuples ``(attach_name, mimetype,
          file_object)`` where  ``attach_name`` is a string with the name will
          appear on the emails attachment, ``mimetype`` is the mimetype of the
          attachment and ``file_object`` is a readable file object with the
          contents of the attachment
        :type attachs: iterable


MailSender settings
===================

These settings define the default constructor values of the :class:`MailSender`
class, and can be used to configure email notifications in your project without
writing any code (for those extensions that use the :class:`MailSender` class):

* :setting:`MAIL_FROM`
* :setting:`MAIL_HOST`

