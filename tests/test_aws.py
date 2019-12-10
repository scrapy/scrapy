# coding=utf-8

import unittest
from io import BytesIO
from email.charset import Charset

from scrapy.aws import SESender


class AWSSenderTest(unittest.TestCase):

    def test_send(self):
        
        # Test Case with Invalid Credentials
        sender = SESender('email-smtp.us-east-1.amazonaws.com', 'username', 'password', 587, "test@test.com")
        result = sender.construct_message(['test@test.com'], "Hello from Scrapy!", "Testing Scrapy Tool To Email Using AWS SES", None, None, 'text/plain', False)
        self.assertEqual(result['Result'], "Unable to send mail")

        # Test Case with Valid Credentials and Invalid Email Addresses
        sender = SESender('email-smtp.us-east-1.amazonaws.com', 'ENTER_USERNAME_HERE', 'ENTER_PASSWORD_HERE', 587, "invalid@email.com")
        result = sender.construct_message(['test@test.com'], "Hello from Scrapy!", "Testing Scrapy Tool To Email Using AWS SES", None, None, 'text/plain', False)
        self.assertEqual(result['Result'], "Unable to send mail")

        # Test Case with Valid Credentials and Valid Email Addresses
        sender = SESender('email-smtp.us-east-1.amazonaws.com', 'ENTER_USERNAME_HERE', 'ENTER_PASSWORD_HERE', 587, "test@test.com")
        result = sender.construct_message(['test@test.com'], "Hello from Scrapy!", "Testing Scrapy Tool To Email Using AWS SES", None, None, 'text/plain', False)
        self.assertEqual(result['Result'], "Mail Sent")
        self.assertEqual(result['To'][0], "test@test.com")
        self.assertEqual(result['CC'], None)
        self.assertEqual(result['Body'], "Testing Scrapy Tool To Email Using AWS SES")
        self.assertEqual(result['Subject'], "Hello from Scrapy!")
    
    def test_send_single_values_to_and_cc(self):

        sender = SESender('email-smtp.us-east-1.amazonaws.com', 'ENTER_USERNAME_HERE', 'ENTER_PASSWORD_HERE', 587, "test@test.com")
        result = sender.construct_message(['test@test.com'], "Hello from Scrapy!", "Testing Scrapy Tool To Email Using AWS SES", ['test@test.com'], None, 'text/plain', False)
        self.assertEqual(result['Result'], "Mail Sent")
        self.assertEqual(result['To'][0], "test@test.com")
        self.assertEqual(result['CC'], "test@test.com")
        self.assertEqual(result['Body'], "Testing Scrapy Tool To Email Using AWS SES")
        self.assertEqual(result['Subject'], "Hello from Scrapy!")

    def test_send_html(self):
        sender = SESender('email-smtp.us-east-1.amazonaws.com', 'ENTER_USERNAME_HERE', 'ENTER_PASSWORD_HERE', 587, "test@test.com")
        result = sender.construct_message(['test@test.com'], "Hello from Scrapy!", '<p>body</p>', ['test@test.com'], None, 'text/html', False)
        self.assertEqual(result['Result'], "Mail Sent")
        self.assertEqual(result['To'][0], "test@test.com")
        self.assertEqual(result['CC'],  "test@test.com")
        self.assertEqual(result['Body'], "<p>body</p>")
        self.assertEqual(result['Subject'], "Hello from Scrapy!")
    
    def test_send_utf8(self):
        subject = u'sübjèçt'
        body = u'bödÿ-àéïöñß'
        sender = SESender('email-smtp.us-east-1.amazonaws.com', 'ENTER_USERNAME_HERE', 'ENTER_PASSWORD_HERE', 587, "test@test.com")
        result = sender.construct_message(['test@test.com'], subject, body, ['test@test.com'], None, 'text/html', False)
        self.assertEqual(result['Result'], "Mail Sent")
        self.assertEqual(result['Subject'], subject)
        self.assertEqual(result['CC'],  "test@test.com")
        self.assertEqual(result['To'][0], "test@test.com")
        self.assertEqual(result['Body'], body)
    
    def test_send_attach_utf8(self):
        subject = u'sübjèçt'
        body = u'bödÿ-àéïöñß'
        attach = BytesIO()
        attach.seek(0)
        attachs = [('attachment', 'text/plain', attach)]

        sender = SESender('email-smtp.us-east-1.amazonaws.com', 'ENTER_USERNAME_HERE', 'ENTER_PASSWORD_HERE', 587, "test@test.com")
        result = sender.construct_message(['test@test.com'], subject, body, ['test@test.com'], attachs, 'text/html', 'utf-8')
        self.assertEqual(result['Result'], "Mail Sent")
        self.assertEqual(result['Subject'], subject)
        self.assertEqual(result['Body'], body)
        self.assertEqual(result['CC'],  "test@test.com")
        self.assertEqual(result['To'][0], "test@test.com")
      
if __name__ == "__main__":
    unittest.main()
