"""
Mail sending helpers

See documentation in docs/topics/email.rst
"""

from __future__ import annotations

import logging
import warnings
from email import encoders as Encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from io import BytesIO
from typing import IO, TYPE_CHECKING, Any

from twisted.internet import ssl
from twisted.internet.defer import Deferred

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    # imports twisted.internet.reactor
    from twisted.mail.smtp import ESMTPSenderFactory
    from twisted.python.failure import Failure

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


# Defined in the email.utils module, but undocumented:
# https://github.com/python/cpython/blob/v3.9.0/Lib/email/utils.py#L42
COMMASPACE = ", "


def _to_bytes_or_none(text: str | bytes | None) -> bytes | None:
    if text is None:
        return None
    return to_bytes(text)


class MailSender:
    def __init__(
        self,
        smtphost: str = "localhost",
        mailfrom: str = "scrapy@localhost",
        smtpuser: str | None = None,
        smtppass: str | None = None,
        smtpport: int = 25,
        smtptls: bool = False,
        smtpssl: bool = False,
        debug: bool = False,
    ):
        self.smtphost: str = smtphost
        self.smtpport: int = smtpport
        self.smtpuser: bytes | None = _to_bytes_or_none(smtpuser)
        self.smtppass: bytes | None = _to_bytes_or_none(smtppass)
        self.smtptls: bool = smtptls
        self.smtpssl: bool = smtpssl
        self.mailfrom: str = mailfrom
        self.debug: bool = debug

    @classmethod
    def from_settings(cls, settings: BaseSettings) -> Self:
        warnings.warn(
            f"{cls.__name__}.from_settings() is deprecated, use from_crawler() instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return cls._from_settings(settings)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls._from_settings(crawler.settings)

    @classmethod
    def _from_settings(cls, settings: BaseSettings) -> Self:
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
        to: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        attachs: Sequence[tuple[str, str, IO[Any]]] = (),
        mimetype: str = "text/plain",
        charset: str | None = None,
        _callback: Callable[..., None] | None = None,
    ) -> Deferred[None] | None:
        from twisted.internet import reactor

        msg: MIMEBase = (
            MIMEMultipart() if attachs else MIMENonMultipart(*mimetype.split("/", 1))
        )

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
            for attach_name, attach_mimetype, f in attachs:
                part = MIMEBase(*attach_mimetype.split("/"))
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

        dfd: Deferred[Any] = self._sendmail(
            rcpts, msg.as_string().encode(charset or "utf-8")
        )
        dfd.addCallback(self._sent_ok, to, cc, subject, len(attachs))
        dfd.addErrback(self._sent_failed, to, cc, subject, len(attachs))
        reactor.addSystemEventTrigger("before", "shutdown", lambda: dfd)
        return dfd

    def _sent_ok(
        self, result: Any, to: list[str], cc: list[str], subject: str, nattachs: int
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
        to: list[str],
        cc: list[str],
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

    def _sendmail(self, to_addrs: list[str], msg: bytes) -> Deferred[Any]:
        from twisted.internet import reactor

        msg_io = BytesIO(msg)
        d: Deferred[Any] = Deferred()

        factory = self._create_sender_factory(to_addrs, msg_io, d)

        if self.smtpssl:
            reactor.connectSSL(
                self.smtphost, self.smtpport, factory, ssl.ClientContextFactory()
            )
        else:
            reactor.connectTCP(self.smtphost, self.smtpport, factory)

        return d

    def _create_sender_factory(
        self, to_addrs: list[str], msg: IO[bytes], d: Deferred[Any]
    ) -> ESMTPSenderFactory:
        from twisted.mail.smtp import ESMTPSenderFactory

        factory_keywords: dict[str, Any] = {
            "heloFallback": True,
            "requireAuthentication": False,
            "requireTransportSecurity": self.smtptls,
            "hostname": self.smtphost,
        }

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
