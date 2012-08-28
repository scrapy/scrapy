from cStringIO import StringIO
import unittest

from scrapy.mail import MailSender, mail_sent
from scrapy.utils.test import get_crawler


class MailSenderTest(unittest.TestCase):

    def setUp(self):
        self.catched_msg = None
        self.crawler = get_crawler()
        self.crawler.signals.connect(self._catch_mail_sent, signal=mail_sent)

    def tearDown(self):
        self.crawler.signals.disconnect(self._catch_mail_sent, signal=mail_sent)

    def test_send(self):
        mailsender = MailSender(debug=True, crawler=self.crawler)
        mailsender.send(to=['test@scrapy.org'], subject='subject', body='body')

        assert self.catched_msg

        self.assertEqual(self.catched_msg['to'], ['test@scrapy.org'])
        self.assertEqual(self.catched_msg['subject'], 'subject')
        self.assertEqual(self.catched_msg['body'], 'body')

        msg = self.catched_msg['msg']
        self.assertEqual(msg['to'], 'test@scrapy.org')
        self.assertEqual(msg['subject'], 'subject')
        self.assertEqual(msg.get_payload(), 'body')

    def test_send_attach(self):
        attach = StringIO()
        attach.write('content')
        attach.seek(0)
        attachs = [('attachment', 'text/plain', attach)]

        mailsender = MailSender(debug=True, crawler=self.crawler)
        mailsender.send(to=['test@scrapy.org'], subject='subject', body='body',
                       attachs=attachs)

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
