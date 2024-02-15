import logging
import smtplib
from email import encoders as Encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.nonmultipart import MIMENonMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate
from io import BytesIO

from scrapy.utils.misc import arg_to_iter

class SESender(object): 

    def __init__(self, AWS_HOST_NAME, AWS_USER_NAME, AWS_PASSWORD, AWS_PORT_NUMBER, FROM_ADDRESS):
        self.host_name = AWS_HOST_NAME
        self.user_name = AWS_USER_NAME
        self.password = AWS_PASSWORD
        self.port_number = AWS_PORT_NUMBER
        self.from_address = FROM_ADDRESS

    def construct_message(self, to, subject, body, cc, attachments, mimetype, charset):

        # Check to see whether attachments exist
        if attachments: 
            message = MIMEMultipart()
        else: 
            message = MIMENonMultipart(*mimetype.split('/', 1))

        to = list(arg_to_iter(to))

        # Construct the message data-structure
        message = MIMEMultipart()

        # Add content to the body
        message['From'] = self.from_address
        message['To'] = COMMASPACE.join(to)
        message['Date'] = formatdate(localtime = True)
        message['Subject'] = subject
        message['Body'] = body
        recipients = to[:]
        
        if cc:
            recipients.extend(cc)
            message['Cc'] = COMMASPACE.join(cc)

        if charset:
            message.set_charset(charset)
        
        if attachments is not None:
            message.attach(MIMEText(body, 'plain', charset or 'us-ascii'))
            for attach_name, mimetype, f in attachments:
                part = MIMEBase(*mimetype.split('/'))
                part.set_payload(f.read())
                Encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment; filename="%s"' \
                    % attach_name)
                message.attach(part)
        else:
            message.attach(MIMEText(body))

        result = self.send_message(recipients, message)

        return result

    def send_message (self, recipients, message_to_send):
        
        try:
            s = smtplib.SMTP(self.host_name, self.port_number)
            s.starttls()
            s.login(self.user_name, self.password)
            s.sendmail(self.from_address, recipients, message_to_send.as_string())
            s.quit()
            
            return {'Result': "Mail Sent", 
                    'To': recipients, 
                    'CC': message_to_send['Cc'],
                    'Body': message_to_send['Body'],
                    'Subject': message_to_send['Subject']
                    }

        except: 

            return {'Result': "Unable to send mail", 
                    'To': recipients, 
                    'CC': message_to_send['Cc'],
                    'Subject': message_to_send['Subject']}






    



    



