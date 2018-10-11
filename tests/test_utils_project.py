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
        self.assertEqual(
            os.path.join('.scrapy', 'somepath'),
            data_path('somepath')
        )
        abspath = os.path.join(os.path.sep, 'absolute', 'path')
        self.assertEqual(abspath, data_path(abspath))

    def test_data_path_inside_project(self):
        with inside_a_project() as proj_path:
            expected = os.path.join(proj_path, '.scrapy', 'somepath')
            self.assertEqual(
                os.path.realpath(expected),
                os.path.realpath(data_path('somepath'))
            )
            abspath = os.path.join(os.path.sep, 'absolute', 'path')
            self.assertEqual(abspath, data_path(abspath))
