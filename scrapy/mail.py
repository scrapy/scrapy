"""
Mail sending helpers

See documentation in docs/topics/email.rst
"""
from cStringIO import StringIO
from email.MIMEMultipart import MIMEMultipart
from email.MIMENonMultipart import MIMENonMultipart
from email.MIMEBase import MIMEBase
from email.MIMEText import MIMEText
from email.Utils import COMMASPACE, formatdate
from email import Encoders

from twisted.internet import defer, reactor
from twisted.mail.smtp import ESMTPSenderFactory

from scrapy import log
from scrapy.core.exceptions import NotConfigured
from scrapy.conf import settings
from scrapy.utils.signal import send_catch_log


# signal sent when message is sent
# args: to, subject, body, cc, attach, msg
mail_sent = object()


class MailSender(object):

    def __init__(self, smtphost=None, mailfrom=None, smtpuser=None, smtppass=None, \
            smtpport=None):
        self.smtphost = smtphost or settings['MAIL_HOST']
        self.smtpport = smtpport or settings.getint('MAIL_PORT')
        self.smtpuser = smtpuser or settings['MAIL_USER']
        self.smtppass = smtppass or settings['MAIL_PASS']
        self.mailfrom = mailfrom or settings['MAIL_FROM']

        if not self.smtphost or not self.mailfrom:
            raise NotConfigured("MAIL_HOST and MAIL_FROM settings are required")

    def send(self, to, subject, body, cc=None, attachs=()):
        if attachs:
            msg = MIMEMultipart()
        else:
            msg = MIMENonMultipart('text', 'plain')
        msg['From'] = self.mailfrom
        msg['To'] = COMMASPACE.join(to)
        msg['Date'] = formatdate(localtime=True)
        msg['Subject'] = subject
        rcpts = to[:]
        if cc:
            rcpts.extend(cc)
            msg['Cc'] = COMMASPACE.join(cc)

        if attachs:
            msg.attach(MIMEText(body))
            for attach_name, mimetype, f in attachs:
                part = MIMEBase(*mimetype.split('/'))
                part.set_payload(f.read())
                Encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment; filename="%s"' \
                    % attach_name)
                msg.attach(part)
        else:
            msg.set_payload(body)

        send_catch_log(signal=mail_sent, to=to, subject=subject, body=body,
                       cc=cc, attach=attachs, msg=msg)

        if settings.getbool('MAIL_DEBUG'):
            log.msg('Debug mail sent OK: To=%s Cc=%s Subject="%s" Attachs=%d' % \
                (to, cc, subject, len(attachs)), level=log.DEBUG)
            return

        dfd = self._sendmail(rcpts, msg.as_string())
        dfd.addCallbacks(self._sent_ok, self._sent_failed,
            callbackArgs=[to, cc, subject, len(attachs)],
            errbackArgs=[to, cc, subject, len(attachs)])
        reactor.addSystemEventTrigger('before', 'shutdown', lambda: dfd)
        return dfd

    def _sent_ok(self, result, to, cc, subject, nattachs):
        log.msg('Mail sent OK: To=%s Cc=%s Subject="%s" Attachs=%d' % \
            (to, cc, subject, nattachs))

    def _sent_failed(self, failure, to, cc, subject, nattachs):
        errstr = str(failure.value)
        log.msg('Unable to send mail: To=%s Cc=%s Subject="%s" Attachs=%d - %s' % \
            (to, cc, subject, nattachs, errstr), level=log.ERROR)

    def _sendmail(self, to_addrs, msg):
        msg = StringIO(msg)
        d = defer.Deferred()
        factory = ESMTPSenderFactory(self.smtpuser, self.smtppass, self.mailfrom, \
            to_addrs, msg, d, heloFallback=True, requireAuthentication=False, \
            requireTransportSecurity=False)
        factory.noisy = False
        reactor.connectTCP(self.smtphost, self.smtpport, factory)
        return d
