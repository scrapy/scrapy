from email.charset import Charset
from io import BytesIO

from twisted.internet import defer
from twisted.internet._sslverify import ClientTLSOptions

from scrapy.mail import MailSender


class TestMailSender:
    def test_send(self):
        mailsender = MailSender(debug=True)
        mailsender.send(
            to=["test@scrapy.org"],
            subject="subject",
            body="body",
            _callback=self._catch_mail_sent,
        )

        assert self.catched_msg

        assert self.catched_msg["to"] == ["test@scrapy.org"]
        assert self.catched_msg["subject"] == "subject"
        assert self.catched_msg["body"] == "body"

        msg = self.catched_msg["msg"]
        assert msg["to"] == "test@scrapy.org"
        assert msg["subject"] == "subject"
        assert msg.get_payload() == "body"
        assert msg.get("Content-Type") == "text/plain"

    def test_send_single_values_to_and_cc(self):
        mailsender = MailSender(debug=True)
        mailsender.send(
            to="test@scrapy.org",
            subject="subject",
            body="body",
            cc="test@scrapy.org",
            _callback=self._catch_mail_sent,
        )

    def test_send_html(self):
        mailsender = MailSender(debug=True)
        mailsender.send(
            to=["test@scrapy.org"],
            subject="subject",
            body="<p>body</p>",
            mimetype="text/html",
            _callback=self._catch_mail_sent,
        )

        msg = self.catched_msg["msg"]
        assert msg.get_payload() == "<p>body</p>"
        assert msg.get("Content-Type") == "text/html"

    def test_send_attach(self):
        attach = BytesIO()
        attach.write(b"content")
        attach.seek(0)
        attachs = [("attachment", "text/plain", attach)]

        mailsender = MailSender(debug=True)
        mailsender.send(
            to=["test@scrapy.org"],
            subject="subject",
            body="body",
            attachs=attachs,
            _callback=self._catch_mail_sent,
        )

        assert self.catched_msg
        assert self.catched_msg["to"] == ["test@scrapy.org"]
        assert self.catched_msg["subject"] == "subject"
        assert self.catched_msg["body"] == "body"

        msg = self.catched_msg["msg"]
        assert msg["to"] == "test@scrapy.org"
        assert msg["subject"] == "subject"

        payload = msg.get_payload()
        assert isinstance(payload, list)
        assert len(payload) == 2

        text, attach = payload
        assert text.get_payload(decode=True) == b"body"
        assert text.get_charset() == Charset("us-ascii")
        assert attach.get_payload(decode=True) == b"content"

    def _catch_mail_sent(self, **kwargs):
        self.catched_msg = {**kwargs}

    def test_send_utf8(self):
        subject = "sübjèçt"
        body = "bödÿ-àéïöñß"
        mailsender = MailSender(debug=True)
        mailsender.send(
            to=["test@scrapy.org"],
            subject=subject,
            body=body,
            charset="utf-8",
            _callback=self._catch_mail_sent,
        )

        assert self.catched_msg
        assert self.catched_msg["subject"] == subject
        assert self.catched_msg["body"] == body

        msg = self.catched_msg["msg"]
        assert msg["subject"] == subject
        assert msg.get_payload(decode=True).decode("utf-8") == body
        assert msg.get_charset() == Charset("utf-8")
        assert msg.get("Content-Type") == 'text/plain; charset="utf-8"'

    def test_send_attach_utf8(self):
        subject = "sübjèçt"
        body = "bödÿ-àéïöñß"
        attach = BytesIO()
        attach.write(body.encode("utf-8"))
        attach.seek(0)
        attachs = [("attachment", "text/plain", attach)]

        mailsender = MailSender(debug=True)
        mailsender.send(
            to=["test@scrapy.org"],
            subject=subject,
            body=body,
            attachs=attachs,
            charset="utf-8",
            _callback=self._catch_mail_sent,
        )

        assert self.catched_msg
        assert self.catched_msg["subject"] == subject
        assert self.catched_msg["body"] == body

        msg = self.catched_msg["msg"]
        assert msg["subject"] == subject
        assert msg.get_charset() == Charset("utf-8")
        assert msg.get("Content-Type") == 'multipart/mixed; charset="utf-8"'

        payload = msg.get_payload()
        assert isinstance(payload, list)
        assert len(payload) == 2

        text, attach = payload
        assert text.get_payload(decode=True).decode("utf-8") == body
        assert text.get_charset() == Charset("utf-8")
        assert attach.get_payload(decode=True).decode("utf-8") == body

    def test_create_sender_factory_with_host(self):
        mailsender = MailSender(debug=False, smtphost="smtp.testhost.com")

        factory = mailsender._create_sender_factory(
            to_addrs=["test@scrapy.org"], msg="test", d=defer.Deferred()
        )

        context = factory.buildProtocol("test@scrapy.org").context
        assert isinstance(context, ClientTLSOptions)
