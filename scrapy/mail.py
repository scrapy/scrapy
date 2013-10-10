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

from twisted.internet import defer, reactor, ssl
from twisted.mail.smtp import ESMTPSenderFactory

from scrapy import log

class MailSender(object):

    def __init__(self, smtphost='localhost', mailfrom='scrapy@localhost',
            smtpuser=None, smtppass=None, smtpport=25, smtptls=False, smtpssl=False, debug=False):
        self.smtphost = smtphost
        self.smtpport = smtpport
        self.smtpuser = smtpuser
        self.smtppass = smtppass
        self.smtptls = smtptls
        self.smtpssl = smtpssl
        self.mailfrom = mailfrom
        self.debug = debug

    @classmethod
    def from_settings(cls, settings):
        return cls(settings['MAIL_HOST'], settings['MAIL_FROM'], settings['MAIL_USER'],
            settings['MAIL_PASS'], settings.getint('MAIL_PORT'),
            settings.getbool('MAIL_TLS'), settings.getbool('MAIL_SSL'))

    def send(self, to, subject, body, cc=None, attachs=(), _callback=None):
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

        if _callback:
            _callback(to=to, subject=subject, body=body, cc=cc, attach=attachs, msg=msg)

        if self.debug:
            log.msg(format='Debug mail sent OK: To=%(mailto)s Cc=%(mailcc)s Subject="%(mailsubject)s" Attachs=%(mailattachs)d',
                    level=log.DEBUG, mailto=to, mailcc=cc, mailsubject=subject, mailattachs=len(attachs))
            return

        dfd = self._sendmail(rcpts, msg.as_string())
        dfd.addCallbacks(self._sent_ok, self._sent_failed,
            callbackArgs=[to, cc, subject, len(attachs)],
            errbackArgs=[to, cc, subject, len(attachs)])
        reactor.addSystemEventTrigger('before', 'shutdown', lambda: dfd)
        return dfd

    def _sent_ok(self, result, to, cc, subject, nattachs):
        log.msg(format='Mail sent OK: To=%(mailto)s Cc=%(mailcc)s '
                       'Subject="%(mailsubject)s" Attachs=%(mailattachs)d',
                mailto=to, mailcc=cc, mailsubject=subject, mailattachs=nattachs)

    def _sent_failed(self, failure, to, cc, subject, nattachs):
        errstr = str(failure.value)
        log.msg(format='Unable to send mail: To=%(mailto)s Cc=%(mailcc)s '
                       'Subject="%(mailsubject)s" Attachs=%(mailattachs)d'
                       '- %(mailerr)s',
                level=log.ERROR, mailto=to, mailcc=cc, mailsubject=subject,
                mailattachs=nattachs, mailerr=errstr)

    def _sendmail(self, to_addrs, msg):
        msg = StringIO(msg)
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
