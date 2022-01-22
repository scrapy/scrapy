import unittest
import os
import tempfile
import shutil
import contextlib

from pytest import warns

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.project import data_path, get_project_settings


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


@contextlib.contextmanager
def set_env(**update):
    modified = set(update.keys()) & set(os.environ.keys())
    update_after = {k: os.environ[k] for k in modified}
    remove_after = frozenset(k for k in update if k not in os.environ)
    try:
        os.environ.update(update)
        yield
    finally:
        os.environ.update(update_after)
        for k in remove_after:
            os.environ.pop(k)


class GetProjectSettingsTestCase(unittest.TestCase):

    def test_valid_envvar(self):
        value = 'tests.test_cmdline.settings'
        envvars = {
            'SCRAPY_SETTINGS_MODULE': value,
        }
        with set_env(**envvars), warns(None) as warnings:
            settings = get_project_settings()
        assert not warnings
        assert settings.get('SETTINGS_MODULE') == value

    def test_invalid_envvar(self):
        envvars = {
            'SCRAPY_FOO': 'bar',
        }
        with set_env(**envvars), warns(None) as warnings:
            get_project_settings()
        assert len(warnings) == 1
        assert warnings[0].category == ScrapyDeprecationWarning
        assert str(warnings[0].message).endswith(': FOO')

    def test_valid_and_invalid_envvars(self):
        value = 'tests.test_cmdline.settings'
        envvars = {
            'SCRAPY_FOO': 'bar',
            'SCRAPY_SETTINGS_MODULE': value,
        }
        with set_env(**envvars), warns(None) as warnings:
            settings = get_project_settings()
        assert len(warnings) == 1
        assert warnings[0].category == ScrapyDeprecationWarning
        assert str(warnings[0].message).endswith(': FOO')
        assert settings.get('SETTINGS_MODULE') == value
