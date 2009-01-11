.. _topics-email:

=============
Sending email
=============

.. module:: scrapy.mail
   :synopsis: Helpers to easily send e-mail.

Although Python makes sending e-mail relatively easy via the `smtplib library`_,
Scrapy provides a couple of light wrappers over it, to make sending e-mail
extra quick.

The code lives in a single module: ``scrapy.mail``.

.. _smtplib library: http://docs.python.org/library/smtplib.html

Quick example
=============

Here's a quick example of how to send an email (without attachments)::

    from scrapy.mail import MailSender

    mailer = MailSender()
    mailer.send(to=["someone@example.com"], "Some subject", "Some body", cc=["another@example.com"])

MailSender class
================

MailSender is the class used to send emails from Scrapy. It's
currently only a warpper over the (IO blocking) smtplib
library but it's gonna be ported to Twisted soon.

.. class:: scrapy.mail.MailSender(smtphost, mailfrom)

    ``smtphost`` is a string with the SMTP host to use for sending the emails

    ``mailfrom`` is a string with the email address to use for sending messages
    (in the ``From:`` header)

.. method:: send(to, subject, body, cc=None, attachs=None)

    Send mail to the given recipients
        
    ``to`` is a list of email recipients

    ``subject`` is a string with the subject of the message

    ``cc`` is a list of emails to CC 

    ``body`` is a string with the body of the message

    ``attachs`` is a list of tuples containing (attach_name, mimetype, file_object) where:
        ``attach_name`` is a string with the name will appear on the emails attachment
        ``mimetype`` is the mimetype of the attachment
        ``file_object`` is a readable file object

