.. _topics-email:

=============
Sending email
=============

.. module:: scrapy.mail
   :synopsis: Helpers to easily send e-mail.

Although Python makes sending e-mail relatively easy via the `smtplib`_
library, Scrapy provides its own class for sending emails which is very easy to
use and it's implemented using `Twisted non-blocking IO`_, to avoid affecting
the crawling performance.

.. _smtplib: http://docs.python.org/library/smtplib.html

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

    ``smtphost`` is a string with the SMTP host to use for sending the emails.
    If omitted, :setting:`MAIL_HOST` will be used.

    ``mailfrom`` is a string with the email address to use for sending messages
    (in the ``From:`` header). If omitted, :setting:`MAIL_FROM` will be used.

.. method:: MailSender.send(to, subject, body, cc=None, attachs=())

    Send mail to the given recipients

    ``to`` is a list of email recipients

    ``subject`` is a string with the subject of the message

    ``cc`` is a list of emails to CC 

    ``body`` is a string with the body of the message

    ``attachs`` is an iterable of tuples (attach_name, mimetype, file_object)
    where:

        ``attach_name`` is a string with the name will appear on the emails attachment
        ``mimetype`` is the mimetype of the attachment
        ``file_object`` is a readable file object


.. _Twisted non-blocking IO: http://twistedmatrix.com/projects/core/documentation/howto/async.html
