from cStringIO import StringIO
import unittest

from scrapy.xlib.pydispatch import dispatcher

from scrapy.conf import settings
from scrapy.mail import MailSender, mail_sent


class MailSenderTest(unittest.TestCase):

    def setUp(self):
        settings.disabled = False
        settings.overrides['MAIL_DEBUG'] = True

        self.catched_msg = None

        dispatcher.connect(self._catch_mail_sent, signal=mail_sent)

    def test_send(self):
        mailsender = MailSender()
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

        mailsender = MailSender()
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

    def tearDown(self):
        del settings.overrides['MAIL_DEBUG']
        settings.disabled = True

    def _catch_mail_sent(self, **kwargs):
        self.catched_msg = dict(**kwargs)


if __name__ == "__main__":
    unittest.main()
