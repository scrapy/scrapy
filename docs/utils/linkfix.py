"""
Mail sending helpers

See documentation in docs/topics/email.rst
"""

import logging

from email import encoders as Encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate
from io import BytesIO

from twisted.internet import defer, reactor, ssl
from twisted.mail.smtp import ESMTPSenderFactory
from twisted.python.versions import Version

from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import to_bytes


logger = logging.getLogger(__name__)


class MailSender:
    def __init__(
        self,
        smtphost="localhost",
        mailfrom="scrapy@localhost",
        smtpuser=None,
        smtppass=None,
        smtpport=25,
        smtptls=False,
        smtpssl=False,
        debug=False,
    ):
        self.smtphost = smtphost
        self.smtpport = smtpport
        self.smtpuser = to_bytes(smtpuser) if smtpuser else None
        self.smtppass = to_bytes(smtppass) if smtppass else None
        self.smtptls = smtptls
        self.smtpssl = smtpssl
        self.mailfrom = mailfrom
        self.debug = debug

    @classmethod
    def from_settings(cls, settings):
        return cls(
            smtphost=settings["MAIL_HOST"],
            mailfrom=settings["MAIL_FROM"],
            smtpuser=settings["MAIL_USER"],
            smtppass=settings["MAIL_PASS"],
            smtpport=settings.getint("MAIL_PORT"),
            smtptls=settings.getbool("MAIL_TLS"),
            smtpssl=settings.getbool("MAIL_SSL"),
        )

    def send(
        self,
        to,
        subject,
        body,
        cc=None,
        attachs=(),
        mimetype="text/plain",
        charset=None,
        _callback=None,
    ):

        if attachs:
            msg = MIMEMultipart()
        else:
            msg = MIMEText(body, mimetype, charset)

        to = arg_to_iter(to)
        cc = arg_to_iter(cc)

        msg["From"] = self.mailfrom
        msg["To"] = COMMASPACE.join(to)
        msg["Date"] = formatdate(localtime=True)
        msg["Subject"] = subject

        rcpts = list(to)
        if cc:
            rcpts.extend(list(cc))
            msg["Cc"] = COMMASPACE.join(cc)

        if charset:
            msg.set_charset(charset)

        if attachs:
            msg.attach(MIMEText(body, mimetype, charset))
            for attachment in attachs:
                attach_name, mimetype, f = attachment
                part = MIMEBase(*mimetype.split("/"))
                part.set_payload(f.read())
                Encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition", "attachment", filename=attach_name
                )
                msg.attach(part)

        if _callback:
            _callback(to=to, subject=subject, body=body, cc=cc, attach=attachs, msg=msg)

        if self.debug:
            logger.debug(
                "Debug mail sent OK: To=%(mailto)s Cc=%(mailcc)s "
                'Subject="%(mailsubject)s" Attachs=%(mailattachs)d',
                {
                    "mailto": to,
                    "mailcc": cc,
                    "mailsubject": subject,
                    "mailattachs": len(attachs),
                },
            )
            return

        d = self._sendmail(rcpts, msg.as_string().encode(charset or "utf-8"))
        d.addCallbacks(
            callback=self._sent_ok,
            errback=self._sent_failed,
            callbackArgs=[to, cc, subject, len(attachs)],
            errbackArgs=[to, cc, subject, len(attachs)],
        )
        reactor.addSystemEventTrigger("before", "shutdown", lambda: d)
        return d

    def _sent_ok(self, result, to, cc, subject, nattachs):
        logger.info(
            "Mail sent OK: To=%(mailto)s Cc=%(mailcc)s "
            'Subject="%(mailsubject)s" Attachs=%(mailattachs)d',
            {
                "mailto": to,
                "mailcc": cc,
                "mailsubject": subject,
                "mailattachs": nattachs,
            },
        )

    def _sent_failed(self, failure, to, cc, subject, nattachs):
        errstr = str(failure.value)
        logger.error(
            "Unable to send mail: To=%(mailto)s Cc=%(mailcc)s "
            'Subject="%(mailsubject)s" Attachs=%(mailattachs)d'
            "- %(mailerr)s",
            {
                "mailto": to,
                "mailcc": cc,
                "mailsubject": subject,
                "mailattachs": nattachs,
                "mailerr": errstr,
            },
        )

    def _sendmail(self, to_addrs, msg):
        d = defer.Deferred()

        factory = ESMTPSenderFactory(
            self.smtphost,
            self.smtpuser,
            to_addrs,
            msg,
            self.smtppass,
            self.smtpport,
            contextFactory=(ssl.ClientContextFactory() if self.smtpssl else None),
            requireAuthentication=False,
            requireTransportSecurity=self.smtptls,
            heloFallback=True,
            hostname=self.smtphost if Version("twisted", 21, 2, 0) <= twisted_version else None,
        )

        factory.protocol = lambda: CustomSMTPClient(factory)
        reactor.connectTCP(self.smtphost, self.smtpport, factory)

        return d


class CustomSMTPClient(object):
    """
    Custom SMTP client class to handle a message sent event.
    """

    def __init__(self, factory):
        self.factory = factory

    def send_message(self, from_addr, to_addrs, msg):
        self.factory.resetDelay()
        d = self.factory.getMailSender(to_addrs, from_addr, msg)
        d.addCallbacks(self._message_sent, self._message_failed)

    def _message_sent(self, response):
        self.factory.protocol = lambda: CustomSMTPClient(self.factory)
        self.factory.deferred.callback(response)

    def _message_failed(self, err):
        self.factory.protocol = lambda: CustomSMTPClient(self.factory)
        self.factory.deferred.errback(err)
