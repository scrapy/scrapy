import shutil
import tempfile
import unittest


class QueuelibTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="queuelib-tests-")
        self.qpath = self.tempfilename()
        self.qdir = self.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def tempfilename(self):
        with tempfile.NamedTemporaryFile(dir=self.tmpdir) as nf:
            return nf.name

    def mkdtemp(self):
        return tempfile.mkdtemp(dir=self.tmpdir)


def track_closed(cls):
    """Wraps a queue class to track down if close() method was called"""

    class TrackingClosed(cls):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.closed = False

        def close(self):
            super().close()
            self.closed = True

    return TrackingClosed
