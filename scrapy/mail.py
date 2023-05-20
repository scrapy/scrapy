"""
Mail sending helpers

See documentation in docs/topics/email.rst
"""
import logging
from email import encoders as Encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from io import BytesIO

from twisted import version as twisted_version
from twisted.internet import defer, reactor, ssl
from twisted.python.versions import Version

from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import to_bytes

logger = logging.getLogger(__name__)


# Defined in the email.utils module, but undocumented:
# https://github.com/python/cpython/blob/v3.9.0/Lib/email/utils.py#L42
COMMASPACE = ", "


def _to_bytes_or_none(text):
    if text is None:
        return None
    return to_bytes(text)


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
        self.smtpuser = _to_bytes_or_none(smtpuser)
        self.smtppass = _to_bytes_or_none(smtppass)
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

    def helperMsgMethod(self, msg, to, subject):
        """
        Helper method that takes a dictionary as an argument
        and populates the from, to, date and subject values
        """

        msg["From"] = self.mailfrom
        msg["To"] = COMMASPACE.join(to)
        msg["Date"] = formatdate(localtime=True)
        msg["Subject"] = subject

    def loggerDebugHelper(self, to, cc, subject, attachs):
        """
        Helper method that populates a debug loger
        with information about a bug. Takes four
        arguments to, cc, subject, and the attachments.
        It doesn't return anything
        """
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

    def send(self, to, subject, body, cc=None, attachs=(),
        mimetype="text/plain", charset=None, _callback=None):
        """
        Method for sending an email with the results to the user. Takes
        as arguments the address to be sent, a subject, the body of the email,
        any attachments in the form of tuple, any cc parties. The type of the 
        email is set by default to text/plain and charset and _callback are
        set by default to none. It doesn't return a value. 
        """
        if attachs:
            msg = MIMEMultipart()
        else:
            msg = MIMENonMultipart(*mimetype.split("/", 1))

        to = list(arg_to_iter(to))
        cc = list(arg_to_iter(cc))

        self.helperMsgMethod(msg, to, subject)

        rcpts = to[:]
        if cc:
            rcpts.extend(cc)
            msg["Cc"] = COMMASPACE.join(cc)

        if charset:
            msg.set_charset(charset)

        if attachs:
            msg.attach(MIMEText(body, "plain", charset or "us-ascii"))
            for attach_name, mimetype, f in attachs:
                part = MIMEBase(*mimetype.split("/"))
                part.set_payload(f.read())
                Encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition", "attachment", filename=attach_name
                )
                msg.attach(part)
        else:
            msg.set_payload(body)

        if _callback:
            _callback(to=to, subject=subject, body=body, cc=cc, attach=attachs, msg=msg)

        if self.debug:
            self.loggerDebugHelper(to, cc, subject, attachs)
            return

        dfd = self._sendmail(rcpts, msg.as_string().encode(charset or "utf-8"))
        dfd.addCallbacks(
            callback=self._sent_ok,
            errback=self._sent_failed,
            callbackArgs=[to, cc, subject, len(attachs)],
            errbackArgs=[to, cc, subject, len(attachs)],
        )
        reactor.addSystemEventTrigger("before", "shutdown", lambda: dfd)
        return dfd

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
        return failure

    def _sendmail(self, to_addrs, msg):
        from twisted.internet import reactor

        msg = BytesIO(msg)
        d = defer.Deferred()

        factory = self._create_sender_factory(to_addrs, msg, d)

        if self.smtpssl:
            reactor.connectSSL(
                self.smtphost, self.smtpport, factory, ssl.ClientContextFactory()
            )
        else:
            reactor.connectTCP(self.smtphost, self.smtpport, factory)

        return d

    def _create_sender_factory(self, to_addrs, msg, d):
        from twisted.mail.smtp import ESMTPSenderFactory

        factory_keywords = {
            "heloFallback": True,
            "requireAuthentication": False,
            "requireTransportSecurity": self.smtptls,
        }

        # Newer versions of twisted require the hostname to use STARTTLS
        if twisted_version >= Version("twisted", 21, 2, 0):
            factory_keywords["hostname"] = self.smtphost

        factory = ESMTPSenderFactory(
            self.smtpuser,
            self.smtppass,
            self.mailfrom,
            to_addrs,
            msg,
            d,
            **factory_keywords
        )
        factory.noisy = False
        return factory
