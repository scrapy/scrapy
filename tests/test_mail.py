# coding=utf-8
import unittest
from io import BytesIO
from email.charset import Charset

from scrapy.mail import create_email_message, MailSender
from tests import mock


class MailSenderTest(unittest.TestCase):
    def test_send(self):
        mailsender = MailSender(debug=True)
        mailsender.send(to=['test@scrapy.org'], subject='subject', body='body',
                        _callback=self._catch_mail_sent)

        assert self.catched_msg

        self.assertEqual(self.catched_msg['to'], ['test@scrapy.org'])
        self.assertEqual(self.catched_msg['subject'], 'subject')
        self.assertEqual(self.catched_msg['body'], 'body')

        msg = self.catched_msg['msg']
        self.assertEqual(msg['to'], 'test@scrapy.org')
        self.assertEqual(msg['subject'], 'subject')
        self.assertEqual(msg.get_payload(), 'body')
        self.assertEqual(msg.get('Content-Type'), 'text/plain')

    def test_send_single_values_to_and_cc(self):
        mailsender = MailSender(debug=True)
        mailsender.send(to='test@scrapy.org', subject='subject', body='body',
                        cc='test@scrapy.org', _callback=self._catch_mail_sent)

    def test_send_html(self):
        mailsender = MailSender(debug=True)
        mailsender.send(to=['test@scrapy.org'], subject='subject',
                        body='<p>body</p>', mimetype='text/html',
                        _callback=self._catch_mail_sent)

        msg = self.catched_msg['msg']
        self.assertEqual(msg.get_payload(), '<p>body</p>')
        self.assertEqual(msg.get('Content-Type'), 'text/html')

    def test_send_attach(self):
        attach = BytesIO()
        attach.write(b'content')
        attach.seek(0)
        attachs = [('attachment', 'text/plain', attach)]

        mailsender = MailSender(debug=True)
        mailsender.send(to=['test@scrapy.org'], subject='subject', body='body',
                       attachs=attachs, _callback=self._catch_mail_sent)

        assert self.catched_msg
        self.assertEqual(self.catched_msg['to'], ['test@scrapy.org'])
        self.assertEqual(self.catched_msg['subject'], 'subject')
        self.assertEqual(self.catched_msg['body'], 'body')

        msg = self.catched_msg['msg']
        self.assertEqual(msg['to'], 'test@scrapy.org')
        self.assertEqual(msg['subject'], 'subject')

        payload = msg.get_payload()
        assert isinstance(payload, list)
        self.assertEqual(len(payload), 2)

        text, attach = payload
        self.assertEqual(text.get_payload(decode=True), b'body')
        self.assertEqual(text.get_charset(), Charset('us-ascii'))
        self.assertEqual(attach.get_payload(decode=True), b'content')

    def _catch_mail_sent(self, **kwargs):
        self.catched_msg = dict(**kwargs)

    def test_send_utf8(self):
        subject = u'sübjèçt'
        body = u'bödÿ-àéïöñß'
        mailsender = MailSender(debug=True)
        mailsender.send(to=['test@scrapy.org'], subject=subject, body=body,
                        charset='utf-8', _callback=self._catch_mail_sent)

        assert self.catched_msg
        self.assertEqual(self.catched_msg['subject'], subject)
        self.assertEqual(self.catched_msg['body'], body)

        msg = self.catched_msg['msg']
        self.assertEqual(msg['subject'], subject)
        self.assertEqual(msg.get_payload(), body)
        self.assertEqual(msg.get_charset(), Charset('utf-8'))
        self.assertEqual(msg.get('Content-Type'), 'text/plain; charset="utf-8"')

    def test_send_attach_utf8(self):
        subject = u'sübjèçt'
        body = u'bödÿ-àéïöñß'
        attach = BytesIO()
        attach.write(body.encode('utf-8'))
        attach.seek(0)
        attachs = [('attachment', 'text/plain', attach)]

        mailsender = MailSender(debug=True)
        mailsender.send(to=['test@scrapy.org'], subject=subject, body=body,
                        attachs=attachs, charset='utf-8',
                        _callback=self._catch_mail_sent)

        assert self.catched_msg
        self.assertEqual(self.catched_msg['subject'], subject)
        self.assertEqual(self.catched_msg['body'], body)

        msg = self.catched_msg['msg']
        self.assertEqual(msg['subject'], subject)
        self.assertEqual(msg.get_charset(), Charset('utf-8'))
        self.assertEqual(msg.get('Content-Type'),
                         'multipart/mixed; charset="utf-8"')

        payload = msg.get_payload()
        assert isinstance(payload, list)
        self.assertEqual(len(payload), 2)

        text, attach = payload
        self.assertEqual(text.get_payload(decode=True).decode('utf-8'), body)
        self.assertEqual(text.get_charset(), Charset('utf-8'))
        self.assertEqual(attach.get_payload(decode=True).decode('utf-8'), body)


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
            'from@scrapy.org', 'to@scrapy.org', subject, body, attachs=attachs, charset='utf-8'
        )
        self.assertEqual(msg['Subject'], subject)
        self.assertEqual(msg.get_charset(), Charset('utf-8'))
        self.assertEqual(msg.get('Content-Type'),
                         'multipart/mixed; charset="utf-8"')

        payload = msg.get_payload()
        assert isinstance(payload, list)
        self.assertEqual(len(payload), 2)

        text, attach = payload
        self.assertEqual(text.get_payload(decode=True).decode('utf-8'), body)
        self.assertEqual(text.get_charset(), Charset('utf-8'))
        self.assertEqual(attach.get_payload(decode=True).decode('utf-8'), body)


if __name__ == "__main__":
    unittest.main()
