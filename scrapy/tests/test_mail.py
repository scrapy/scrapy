import unittest
from io import BytesIO

from scrapy.mail import MailSender

class MailSenderTest(unittest.TestCase):

    def test_send(self):
        mailsender = MailSender(debug=True)
        mailsender.send(to=['test@scrapy.org'], subject='subject', body='body', _callback=self._catch_mail_sent)

        assert self.catched_msg

        self.assertEqual(self.catched_msg['to'], ['test@scrapy.org'])
        self.assertEqual(self.catched_msg['subject'], 'subject')
        self.assertEqual(self.catched_msg['body'], 'body')

        msg = self.catched_msg['msg']
        self.assertEqual(msg['to'], 'test@scrapy.org')
        self.assertEqual(msg['subject'], 'subject')
        self.assertEqual(msg.get_payload(), 'body')
        self.assertEqual(msg.get('Content-Type'), 'text/plain')

    def test_send_html(self):
        mailsender = MailSender(debug=True)
        mailsender.send(to=['test@scrapy.org'], subject='subject', body='<p>body</p>', mimetype='text/html', _callback=self._catch_mail_sent)

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
        self.assertEqual(text.get_payload(decode=True), 'body')
        self.assertEqual(attach.get_payload(decode=True), 'content')

    def _catch_mail_sent(self, **kwargs):
        self.catched_msg = dict(**kwargs)


if __name__ == "__main__":
    unittest.main()
