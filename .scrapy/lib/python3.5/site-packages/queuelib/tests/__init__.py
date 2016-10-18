import unittest, tempfile, shutil

class QueuelibTestCase(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="queuelib-tests-")
        self.qpath = self.mktemp()
        self.qdir = self.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def mktemp(self):
        return tempfile.mktemp(dir=self.tmpdir)

    def mkdtemp(self):
        return tempfile.mkdtemp(dir=self.tmpdir)
