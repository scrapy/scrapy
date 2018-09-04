# coding=utf-8
import unittest
from email.charset import Charset
from io import BytesIO

from scrapy.mail import create_email_message, SESMailSender
from tests import mock


class SESMailSenderTest(unittest.TestCase):
    def test_raise_error_if_aws_credentials_are_not_provided(self):
        with self.assertRaises(TypeError):
            sender = SESMailSender()
        with self.assertRaises(TypeError):
            sender = SESMailSender('JUST_ONE_CREDENTIAL')

        # This should work
        sender = SESMailSender('aws_access_key', 'aws_secret_key')

    @mock.patch('boto.connect_ses')
    def test_if_debug_do_not_send_message(self, boto_connect_mock):
        sender = SESMailSender('aws_access_key', 'aws_secret_key', debug=True)
        sender.send('to@scrapy.org', 'subject', 'body')
        boto_connect_mock.assert_not_called()

    @mock.patch('boto.connect_ses')
    def test_send_message_if_not_debug(self, boto_connect_mock):
        ses_connection_mock = mock.MagicMock()
        # Just need to have this method available in mock
        ses_connection_mock.send_raw_email.return_value = lambda x: x

        boto_connect_mock.return_value = ses_connection_mock

        sender = SESMailSender('aws_access_key', 'aws_secret_key')
        sender.send('to@scrapy.org', 'subject', 'body')

        ses_connection_mock.send_raw_email.assert_called_once()


class CreateMessageTestCase(unittest.TestCase):
    def test_message_with_minimal_values(self):
        msg = create_email_message(
            'from@scrapy.org', 'test@scrapy.org', 'subject', 'content'
        )
        self.assertEqual(msg['From'], 'from@scrapy.org')
        self.assertEqual(msg['To'], 'test@scrapy.org')
        self.assertEqual(msg['Subject'], 'subject')
        self.assertEqual(msg['Cc'], None)
        self.assertEqual(msg['Content-Type'], 'text/plain')
        self.assertEqual(msg.get_payload(), 'content')

    def test_message_with_cc(self):
        msg = create_email_message(
            'from@scrapy.org', 'test@scrapy.org', 'subject', 'content', 'cc@scrapy.org'
        )
        self.assertEqual(msg['Cc'], 'cc@scrapy.org')

    def test_message_with_more_recipients(self):
        to = ['destination1@scrapy.org', 'destination2@scrapy.org']
        cc = ['cc1@scrapy.org', 'cc2@scrapy.org']

        msg = create_email_message('from@scrapy.org', to, 'subject', 'content', cc)
        self.assertEqual(msg['To'], ', '.join(to))
        self.assertEqual(msg['Cc'], ', '.join(cc))

    def test_html_message(self):
        msg = create_email_message(
            'from@scrapy.org',
            'to@scrapy.org',
            'subject',
            '<h1>content</h1>',
            mimetype='text/html',
        )
        self.assertEqual(msg['Content-Type'], 'text/html')
        self.assertEqual(msg.get_payload(), '<h1>content</h1>')

    def test_message_with_attach(self):
        attach = BytesIO()
        attach.write(b'content')
        attach.seek(0)
        attachs = [('attachment', 'text/plain', attach)]

        msg = create_email_message(
            'from@scrapy.org', 'to@scrapy.org', 'subject', 'body', attachs=attachs
        )
        payload = msg.get_payload()
        assert isinstance(payload, list)
        self.assertEqual(len(payload), 2)

        text, attach = payload
        self.assertEqual(text.get_payload(decode=True), b'body')
        self.assertEqual(text.get_charset(), Charset('us-ascii'))
        self.assertEqual(attach.get_payload(decode=True), b'content')

    def test_utf8_message(self):
        subject = u'sübjèçt'
        body = u'bödÿ-àéïöñß'

        msg = create_email_message(
            'from@scrapy.org', 'to@scrapy.org', subject, body, charset='utf-8'
        )
        self.assertEqual(msg['Subject'], subject)
        self.assertEqual(msg.get_payload(), body)
        self.assertEqual(msg.get_charset(), Charset('utf-8'))
        self.assertEqual(msg.get('Content-Type'), 'text/plain; charset="utf-8"')

    def test_utf8_message_attach(self):
        subject = u'sübjèçt'
        body = u'bödÿ-àéïöñß'
        attach = BytesIO()
        attach.write(body.encode('utf-8'))
        attach.seek(0)
        attachs = [('attachment', 'text/plain', attach)]

        msg = create_email_message(
            'from@scrapy.org',
            'to@scrapy.org',
            subject,
            body,
            attachs=attachs,
            charset='utf-8',
        )
        self.assertEqual(msg['Subject'], subject)
        self.assertEqual(msg.get_charset(), Charset('utf-8'))
        self.assertEqual(msg.get('Content-Type'), 'multipart/mixed; charset="utf-8"')

        payload = msg.get_payload()
        assert isinstance(payload, list)
        self.assertEqual(len(payload), 2)

        text, attach = payload
        self.assertEqual(text.get_payload(decode=True).decode('utf-8'), body)
        self.assertEqual(text.get_charset(), Charset('utf-8'))
        self.assertEqual(attach.get_payload(decode=True).decode('utf-8'), body)


if __name__ == "__main__":
    unittest.main()
