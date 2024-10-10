from unittest import mock

from twisted.trial import unittest
from twisted.web.test.requesthelper import DummyRequest

from scrapy.utils import benchserver


class TestBenchServer(unittest.TestCase):
    def setUp(self):
        self.root = benchserver.Root()

    def test_getarg(self):
        request = DummyRequest(b"/")
        request.args = {b"total": [b"200"]}
        result = benchserver._getarg(request, b"total", 100, int)
        self.assertEqual(result, 200)

    def test_getarg_default(self):
        request = DummyRequest(b"/")
        request.args = {}
        result = benchserver._getarg(request, b"total", 100, int)
        self.assertEqual(result, 100)

    def test_render(self):
        request = DummyRequest(b"/")
        request.args = {b"total": [b"200"], b"show": [b"20"]}
        self.root.render(request)
        response_body = b"".join(request.written)

        self.assertIn(b"<html>", response_body)
        self.assertIn(b"</html>", response_body)
        self.assertIn(b"<body>", response_body)
        self.assertIn(b"</body>", response_body)
        self.assertIn(b"follow", response_body)

        self.assertEqual(response_body.count(b"<a "), 20)

        for line in response_body.split(b"<br>")[:-1]:
            self.assertRegex(line, rb"<a href='/follow\?.*n=\d+'>follow \d+</a>")
            link_number = int(line.split(b"follow ")[1].split(b"</a>")[0])
            self.assertTrue(
                1 <= link_number <= 200, f"Link number {link_number} is out of range"
            )

    def test_getChild(self):
        request = DummyRequest(b"/")
        child = self.root.getChild("name", request)
        self.assertEqual(child, self.root)

    @mock.patch("twisted.internet.reactor.callWhenRunning")
    @mock.patch("twisted.internet.reactor.listenTCP")
    @mock.patch("twisted.internet.reactor.run")
    def test_main(self, mock_run, mock_listenTCP, mock_callWhenRunning):
        benchserver.main()
        mock_listenTCP.assert_called_once()
        mock_run.assert_called_once()
        mock_callWhenRunning.assert_called_once_with(mock.ANY)
