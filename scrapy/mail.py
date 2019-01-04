"""
Mail sending helpers

See documentation in docs/topics/email.rst
"""
import logging

try:
    from cStringIO import StringIO as BytesIO
except ImportError:
    from io import BytesIO
import six

from email.utils import COMMASPACE, formatdate
from six.moves.email_mime_multipart import MIMEMultipart
from six.moves.email_mime_text import MIMEText
from six.moves.email_mime_base import MIMEBase
if six.PY2:
    from email.MIMENonMultipart import MIMENonMultipart
    from email import Encoders
else:
    from email.mime.nonmultipart import MIMENonMultipart
    from email import encoders as Encoders

from twisted.internet import defer, reactor, ssl

from scrapy.utils.misc import arg_to_iter
from scrapy.utils.python import to_bytes

logger = logging.getLogger(__name__)


def _to_bytes_or_none(text):
    if text is None:
        return None
    return to_bytes(text)


class MailSender(object):
    """MailSender is the preferred class to use for sending emails from Scrapy,
    as it uses `Twisted non-blocking IO`_, like the rest of the framework.

    :param smtphost: the SMTP host to use for sending the emails. If omitted,
                     the :setting:`MAIL_HOST` setting will be used.
    :type smtphost: str

    :param mailfrom: the address used to send emails (in the ``From:`` header).
                     If omitted, the :setting:`MAIL_FROM` setting will be used.
    :type mailfrom: str

    :param smtpuser: the SMTP user. If omitted, the :setting:`MAIL_USER`
                     setting will be used. If not given, no SMTP authentication
                     will be performed.
    :type smtphost: str or bytes

    :param smtppass: the SMTP pass for authentication.
    :type smtppass: str or bytes

    :param smtpport: the SMTP port to connect to
    :type smtpport: int

    :param smtptls: enforce using SMTP STARTTLS
    :type smtptls: boolean

    :param smtpssl: enforce using a secure SSL connection
    :type smtpssl: boolean

    .. _Twisted non-blocking IO: https://twistedmatrix.com/documents/current/core/howto/defer-intro.html
    """

    def __init__(self, smtphost='localhost', mailfrom='scrapy@localhost',
            smtpuser=None, smtppass=None, smtpport=25, smtptls=False, smtpssl=False, debug=False):
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
        """Instantiate using a Scrapy settings object, which will respect
        :ref:`these Scrapy settings <topics-email-settings>`.

        :param settings: the e-mail recipients
        :type settings: :class:`scrapy.settings.Settings` object
        """
        return cls(settings['MAIL_HOST'], settings['MAIL_FROM'], settings['MAIL_USER'],
            settings['MAIL_PASS'], settings.getint('MAIL_PORT'),
            settings.getbool('MAIL_TLS'), settings.getbool('MAIL_SSL'))

    def send(self, to, subject, body, cc=None, attachs=(), mimetype='text/plain', charset=None, _callback=None):
        """Send email to the given recipients.

        :param to: the e-mail recipients
        :type to: str or list of str

        :param subject: the subject of the e-mail
        :type subject: str

        :param cc: the e-mails to CC
        :type cc: str or list of str

        :param body: the e-mail body
        :type body: str

        :param attachs: an iterable of tuples ``(attach_name, mimetype,
                        file_object)`` where  ``attach_name`` is a string with
                        the name that will appear on the e-mail's attachment,
                        ``mimetype`` is the mimetype of the attachment and
                        ``file_object`` is a readable file object with the
                        contents of the attachment
        :type attachs: iterable

        :param mimetype: the MIME type of the e-mail
        :type mimetype: str

        :param charset: the character encoding to use for the e-mail contents
        :type charset: str
        """
        if attachs:
            msg = MIMEMultipart()
        else:
            msg = MIMENonMultipart(*mimetype.split('/', 1))

        to = list(arg_to_iter(to))
        cc = list(arg_to_iter(cc))

        msg['From'] = self.mailfrom
        msg['To'] = COMMASPACE.join(to)
        msg['Date'] = formatdate(localtime=True)
        msg['Subject'] = subject
        rcpts = to[:]
        if cc:
            rcpts.extend(cc)
            msg['Cc'] = COMMASPACE.join(cc)

        if charset:
            msg.set_charset(charset)

        if attachs:
            msg.attach(MIMEText(body, 'plain', charset or 'us-ascii'))
            for attach_name, mimetype, f in attachs:
                part = MIMEBase(*mimetype.split('/'))
                part.set_payload(f.read())
                Encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment; filename="%s"' \
                    % attach_name)
                msg.attach(part)
        else:
            msg.set_payload(body)

        if _callback:
            _callback(to=to, subject=subject, body=body, cc=cc, attach=attachs, msg=msg)

        if self.debug:
            logger.debug('Debug mail sent OK: To=%(mailto)s Cc=%(mailcc)s '
                         'Subject="%(mailsubject)s" Attachs=%(mailattachs)d',
                         {'mailto': to, 'mailcc': cc, 'mailsubject': subject,
                          'mailattachs': len(attachs)})
            return

        dfd = self._sendmail(rcpts, msg.as_string().encode(charset or 'utf-8'))
        dfd.addCallbacks(self._sent_ok, self._sent_failed,
            callbackArgs=[to, cc, subject, len(attachs)],
            errbackArgs=[to, cc, subject, len(attachs)])
        reactor.addSystemEventTrigger('before', 'shutdown', lambda: dfd)
        return dfd

    def _sent_ok(self, result, to, cc, subject, nattachs):
        logger.info('Mail sent OK: To=%(mailto)s Cc=%(mailcc)s '
                    'Subject="%(mailsubject)s" Attachs=%(mailattachs)d',
                    {'mailto': to, 'mailcc': cc, 'mailsubject': subject,
                     'mailattachs': nattachs})

    def _sent_failed(self, failure, to, cc, subject, nattachs):
        errstr = str(failure.value)
        logger.error('Unable to send mail: To=%(mailto)s Cc=%(mailcc)s '
                     'Subject="%(mailsubject)s" Attachs=%(mailattachs)d'
                     '- %(mailerr)s',
                     {'mailto': to, 'mailcc': cc, 'mailsubject': subject,
                      'mailattachs': nattachs, 'mailerr': errstr})

    def _sendmail(self, to_addrs, msg):
        # Import twisted.mail here because it is not available in python3
        from twisted.mail.smtp import ESMTPSenderFactory
        msg = BytesIO(msg)
        d = defer.Deferred()
        factory = ESMTPSenderFactory(self.smtpuser, self.smtppass, self.mailfrom, \
            to_addrs, msg, d, heloFallback=True, requireAuthentication=False, \
            requireTransportSecurity=self.smtptls)
        factory.noisy = False

        if self.smtpssl:
            reactor.connectSSL(self.smtphost, self.smtpport, factory, ssl.ClientContextFactory())
        else:
            reactor.connectTCP(self.smtphost, self.smtpport, factory)

        return d
