import re
from six.moves import cStringIO
from mock import patch
from twisted.trial import unittest

import scrapy.commands.deploy as deploy
from scrapy.exceptions import UsageError
from scrapy.tests.test_commands import CommandMockTest


@patch('urllib2.install_opener')
class DeployMockTest(CommandMockTest, unittest.TestCase):

    Command = deploy.Command

    def test_wrong_target(self, install_opener_mock):
        self.assertRaisesRegexp(UsageError, r'^Unknown target: wrong$', self.run_command, ['wrong'])

    @patch('scrapy.commands.deploy._get_targets', autospec=True)
    def test_list_targets(self, _get_targets_mock, install_opener_mock):
        _get_targets_mock.return_value = {
            'target1': {'url': 'url1'},
            'target2': {'url': 'url2'},
        }
        stream = cStringIO()
        with patch('sys.stdout') as stdout_mock:
            stdout_mock.write = stream.write
            self.run_command(['--list-targets'])
        # We need to sort output strings and replace arbitrary number of spaces with 1 space to make comparison exact
        sorted_output = '\n'.join(x for x in sorted(re.sub(r'\s{2,}', ' ', stream.getvalue()).splitlines()) if x.strip())
        self.assertEqual(sorted_output, 'target1 url1\ntarget2 url2')

    @patch('urllib2.urlopen', autospec=True)
    @patch('scrapy.commands.deploy._get_targets', autospec=True)
    def test_list_projects(self, _get_targets_mock, urlopen_mock, install_opener_mock):
        urlopen_mock.return_value = cStringIO('{"projects": ["project1", "project2"]}')
        _get_targets_mock.return_value = {
            'target1': {'url': 'http://localhost/target1'},
            'target2': {'url': 'http://localhost/target2'},
        }
        stream = cStringIO()
        with patch('sys.stdout') as stdout_mock:
            stdout_mock.write = stream.write
            self.run_command(['--list-projects', 'target1'])
        self.assertEqual(stream.getvalue().strip(), 'project1\nproject2')

    @patch('scrapy.commands.deploy._build_egg', autospec=True)
    @patch('shutil.copyfile', autospec=True)
    @patch('shutil.rmtree', autospec=True)
    def test_build_egg(self, rmtree_mock, copyfile_mock, _build_egg_mock, install_opener_mock):
        _build_egg_mock.return_value = ('egg', '/egg_temp_dir')
        stream = cStringIO()
        with patch('sys.stderr') as stdout_mock:
            stdout_mock.write = stream.write
            self.run_command(['--build-egg', '/target/egg'])
        self.assertEqual(stream.getvalue().strip(), 'Writing egg to /target/egg')
        self.assertEqual(copyfile_mock.call_count, 1)
        self.assertEqual(copyfile_mock.call_args[0], ('egg', '/target/egg'))
        self.assertEqual(rmtree_mock.call_count, 1)
        self.assertEqual(rmtree_mock.call_args[0], ('/egg_temp_dir',))
