import smtplib

from email.MIMEMultipart import MIMEMultipart
from email.MIMEBase import MIMEBase
from email.MIMEText import MIMEText
from email.Utils import COMMASPACE, formatdate
from email import Encoders

from scrapy import log
from scrapy.core.exceptions import NotConfigured
from scrapy.conf import settings

class MailSender(object):

    def __init__(self, smtphost=None, mailfrom=None):
        self.smtphost = smtphost if smtphost else settings['MAIL_HOST']
        self.mailfrom = mailfrom if mailfrom else settings['MAIL_FROM']

        if not self.smtphost or not self.mailfrom:
            raise NotConfigured("MAIL_HOST and MAIL_FROM settings are required")

    def send(self, to, subject, body, cc=None, attachs=None):
        """
        Send mail to the given recipients
        
        - to: must be a list of email recipients
        - attachs must be a list of tuples: (attach_name, mimetype, file_object)
        - body and subjet must be a string
        """

        msg = MIMEMultipart()
        msg['From'] = self.mailfrom
        msg['To'] = COMMASPACE.join(to)
        msg['Date'] = formatdate(localtime=True)
        msg['Subject'] = subject
        rcpts = to[:]
        if cc:
            rcpts.extend(cc)
            msg['Cc'] = COMMASPACE.join(cc)

        msg.attach(MIMEText(body))

        for attach_name, mimetype, f in (attachs or []):
            part = MIMEBase(*mimetype.split('/'))
            part.set_payload(f.read())
            Encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment; filename="%s"' % attach_name)
            msg.attach(part)

        smtp = smtplib.SMTP(self.smtphost)
        smtp.sendmail(self.mailfrom, rcpts, msg.as_string())
        log.msg('Mail sent: To=%s Cc=%s Subject="%s"' % (to, cc, subject))
        smtp.close()

