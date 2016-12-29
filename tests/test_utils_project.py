import unittest
import os
import tempfile
import shutil
import contextlib
from scrapy.utils.project import data_path


@contextlib.contextmanager
def inside_a_project():
    prev_dir = os.getcwd()
    project_dir = tempfile.mkdtemp()

    try:
        os.chdir(project_dir)
        with open('scrapy.cfg', 'w') as f:
            # create an empty scrapy.cfg
            f.close()

        yield project_dir
    finally:
        os.chdir(prev_dir)
        shutil.rmtree(project_dir)


class ProjectUtilsTest(unittest.TestCase):
    def test_data_path_outside_project(self):
        self.assertEquals('.scrapy/somepath', data_path('somepath'))
        self.assertEquals('/absolute/path', data_path('/absolute/path'))

    def test_data_path_inside_project(self):
        with inside_a_project() as proj_path:
            expected = os.path.join(proj_path, '.scrapy', 'somepath')
            self.assertEquals(expected, data_path('somepath'))
            self.assertEquals('/absolute/path', data_path('/absolute/path'))
