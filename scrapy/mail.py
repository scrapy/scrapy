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


def create_email_message(mailfrom, to, subject, body, cc=None, attachs=(), mimetype='text/plain', charset=None):
    if attachs:
        msg = MIMEMultipart()
    else:
        msg = MIMENonMultipart(*mimetype.split('/', 1))

    to = list(arg_to_iter(to))
    cc = list(arg_to_iter(cc))

    msg['From'] = mailfrom
    msg['To'] = COMMASPACE.join(to)

    if cc:
        msg['Cc'] = COMMASPACE.join(cc)

    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject

    if charset:
        msg.set_charset(charset)

    if attachs:
        msg.attach(MIMEText(body, 'plain', charset or 'us-ascii'))
        for attach_name, mimetype, f in attachs:
            part = MIMEBase(*mimetype.split('/'))
            part.set_payload(f.read())
            Encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition', 'attachment; filename="%s"' % attach_name)
            msg.attach(part)
    else:
        msg.set_payload(body)

    return msg


class BaseMailSender(object):

    @classmethod
    def from_crawler(cls, crawler):
        return cls.from_settings(crawler.settings)

    @classmethod
    def from_settings(cls, **kwargs):
        raise NotImplementedError

    def send(self, to, subject, body, cc=None, attachs=(), mimetype='text/plain', charset=None, _callback=None):
        raise NotImplementedError


class MailSender(BaseMailSender):

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
        return cls(
            smtphost=settings['MAIL_HOST'],
            mailfrom=settings['MAIL_FROM'],
            smtpuser=settings['MAIL_USER'],
            smtppass=settings['MAIL_PASS'],
            smtpport=settings.getint('MAIL_PORT'),
            smtptls=settings.getbool('MAIL_TLS'),
            smtpssl=settings.getbool('MAIL_SSL'),
        )

    def send(self, to, subject, body, cc=None, attachs=(), mimetype='text/plain', charset=None, _callback=None):
        msg = create_email_message(self.mailfrom, to, subject, body, cc, attachs, mimetype, charset)

        if _callback:
            _callback(to=to, subject=subject, body=body, cc=cc, attach=attachs, msg=msg)

        if self.debug:
            logger.debug('Debug mail sent OK: To=%(mailto)s Cc=%(mailcc)s '
                         'Subject="%(mailsubject)s" Attachs=%(mailattachs)d',
                         {'mailto': to, 'mailcc': cc, 'mailsubject': subject,
                          'mailattachs': len(attachs)})
            return

        rcpts = to[:]
        if cc:
            rcpts.extend(cc)

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


class SESMailSender(BaseMailSender):

    def __init__(self, aws_access_key, aws_secret_key, aws_region, mailfrom='scrapy@localhost', debug=False):
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.aws_region = aws_region
        self.mailfrom = mailfrom
        self.debug = debug

    @classmethod
    def from_settings(cls, settings):
        return cls(
            aws_access_key=settings['AWS_ACCESS_KEY_ID'],
            aws_secret_key=settings['AWS_SECRET_ACCESS_KEY'],
            aws_region=settings['AWS_REGION'],
            mailfrom=settings['MAIL_FROM']
        )

    def send(self, to, subject, body, cc=None, attachs=(), mimetype='text/plain', charset=None):
        import boto3

        msg = create_email_message(
            self.mailfrom, to, subject, body, cc, attachs, mimetype, charset)

        if self.debug:
            logger.debug('Debug mail sent OK: To=%(mailto)s Cc=%(mailcc)s '
                         'Subject="%(mailsubject)s" Attachs=%(mailattachs)d',
                         {'mailto': to, 'mailcc': cc, 'mailsubject': subject,
                          'mailattachs': len(attachs)})
            return

        ses_client = boto3.client(
            'ses',
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            region_name=self.aws_region
        )
        ses_client.send_raw_email(
            RawMessage={
                'Data': msg.as_string()
            }
        )
