"""
Mail sending helpers

See documentation in docs/topics/email.rst
"""

from __future__ import annotations

import logging
from email import encoders as Encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from io import BytesIO
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from twisted import version as twisted_version
from twisted.internet import ssl
from twisted.internet.defer import Deferred
from twisted.python.failure import Failure
from twisted.python.versions import Version

from scrapy.settings import BaseSettings
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    # imports twisted.internet.reactor
    from twisted.mail.smtp import ESMTPSenderFactory

    # typing.Self requires Python 3.11
    from typing_extensions import Self

logger = logging.getLogger(__name__)


# Defined in the email.utils module, but undocumented:
# https://github.com/python/cpython/blob/v3.9.0/Lib/email/utils.py#L42
COMMASPACE = ", "


def _to_bytes_or_none(text: Union[str, bytes, None]) -> Optional[bytes]:
    if text is None:
        return None
    return to_bytes(text)


class MailSender:
    def __init__(
        self,
        smtphost: str = "localhost",
        mailfrom: str = "scrapy@localhost",
        smtpuser: Optional[str] = None,
        smtppass: Optional[str] = None,
        smtpport: int = 25,
        smtptls: bool = False,
        smtpssl: bool = False,
        debug: bool = False,
    ):
        self.smtphost: str = smtphost
        self.smtpport: int = smtpport
        self.smtpuser: Optional[bytes] = _to_bytes_or_none(smtpuser)
        self.smtppass: Optional[bytes] = _to_bytes_or_none(smtppass)
        self.smtptls: bool = smtptls
        self.smtpssl: bool = smtpssl
        self.mailfrom: str = mailfrom
        self.debug: bool = debug

    @classmethod
    def from_settings(cls, settings: BaseSettings) -> Self:
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
        to: Union[str, List[str]],
        subject: str,
        body: str,
        cc: Union[str, List[str], None] = None,
        attachs: Sequence[Tuple[str, str, IO]] = (),
        mimetype: str = "text/plain",
        charset: Optional[str] = None,
        _callback: Optional[Callable[..., None]] = None,
    ) -> Optional[Deferred]:
        from twisted.internet import reactor

        msg: MIMEBase
        if attachs:
            msg = MIMEMultipart()
        else:
            msg = MIMENonMultipart(*mimetype.split("/", 1))

        to = list(arg_to_iter(to))
        cc = list(arg_to_iter(cc))

        msg["From"] = self.mailfrom
        msg["To"] = COMMASPACE.join(to)
        msg["Date"] = formatdate(localtime=True)
        msg["Subject"] = subject
        rcpts = to[:]
        if cc:
            rcpts.extend(cc)
            msg["Cc"] = COMMASPACE.join(cc)

        if attachs:
            if charset:
                msg.set_charset(charset)
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
            msg.set_payload(body, charset)

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
            return None

        dfd = self._sendmail(rcpts, msg.as_string().encode(charset or "utf-8"))
        dfd.addCallback(self._sent_ok, to, cc, subject, len(attachs))
        dfd.addErrback(self._sent_failed, to, cc, subject, len(attachs))
        reactor.addSystemEventTrigger("before", "shutdown", lambda: dfd)
        return dfd

    def _sent_ok(
        self, result: Any, to: List[str], cc: List[str], subject: str, nattachs: int
    ) -> None:
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

    def _sent_failed(
        self,
        failure: Failure,
        to: List[str],
        cc: List[str],
        subject: str,
        nattachs: int,
    ) -> Failure:
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

    def _sendmail(self, to_addrs: List[str], msg: bytes) -> Deferred:
        from twisted.internet import reactor

        msg_io = BytesIO(msg)
        d: Deferred = Deferred()

        factory = self._create_sender_factory(to_addrs, msg_io, d)

        if self.smtpssl:
            reactor.connectSSL(
                self.smtphost, self.smtpport, factory, ssl.ClientContextFactory()
            )
        else:
            reactor.connectTCP(self.smtphost, self.smtpport, factory)

        return d

    def _create_sender_factory(
        self, to_addrs: List[str], msg: IO, d: Deferred
    ) -> ESMTPSenderFactory:
        from twisted.mail.smtp import ESMTPSenderFactory

        factory_keywords: Dict[str, Any] = {
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
            **factory_keywords,
        )
        factory.noisy = False
        return factory
