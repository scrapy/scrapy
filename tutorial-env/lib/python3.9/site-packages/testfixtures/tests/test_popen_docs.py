# NB: This file is used in the documentation, if you make changes, ensure
#     you update the line numbers in popen.txt!

from subprocess import Popen, PIPE


def my_func():
    process = Popen(['svn', 'ls', '-R', 'foo'], stdout=PIPE, stderr=PIPE)
    out, err = process.communicate()
    if process.returncode:
        raise RuntimeError('something bad happened')
    return out

dotted_path = 'testfixtures.tests.test_popen_docs.Popen'

from unittest import TestCase

from testfixtures.mock import call
from testfixtures import Replacer, ShouldRaise, compare, SequenceComparison
from testfixtures.popen import MockPopen, PopenBehaviour


class TestMyFunc(TestCase):

    def setUp(self):
        self.Popen = MockPopen()
        self.r = Replacer()
        self.r.replace(dotted_path, self.Popen)
        self.addCleanup(self.r.restore)

    def test_example(self):
        # set up
        self.Popen.set_command('svn ls -R foo', stdout=b'o', stderr=b'e')

        # testing of results
        compare(my_func(), b'o')

        # testing calls were in the right order and with the correct parameters:
        process = call.Popen(['svn', 'ls', '-R', 'foo'], stderr=PIPE, stdout=PIPE)
        compare(Popen.all_calls, expected=[
            process,
            process.communicate()
        ])

    def test_example_bad_returncode(self):
        # set up
        Popen.set_command('svn ls -R foo', stdout=b'o', stderr=b'e',
                          returncode=1)

        # testing of error
        with ShouldRaise(RuntimeError('something bad happened')):
            my_func()

    def test_communicate_with_input(self):
        # setup
        Popen = MockPopen()
        Popen.set_command('a command')
        # usage
        process = Popen('a command', stdout=PIPE, stderr=PIPE, shell=True)
        out, err = process.communicate('foo')
        # test call list
        compare(Popen.all_calls, expected=[
                process.root_call,
                process.root_call.communicate('foo'),
        ])

    def test_read_from_stdout_and_stderr(self):
        # setup
        Popen = MockPopen()
        Popen.set_command('a command', stdout=b'foo', stderr=b'bar')
        # usage
        process = Popen('a command', stdout=PIPE, stderr=PIPE, shell=True)
        compare(process.stdout.read(), expected=b'foo')
        compare(process.stderr.read(), expected=b'bar')

    def test_write_to_stdin(self):
        # setup
        Popen = MockPopen()
        Popen.set_command('a command')
        # usage
        process = Popen('a command', stdin=PIPE, shell=True)
        process.stdin.write('some text')
        process.stdin.close()
        # test call list
        compare(Popen.all_calls, expected=[
            process.root_call,
            process.root_call.stdin.write('some text'),
            process.root_call.stdin.close(),
        ])

    def test_wait_and_return_code(self):
        # setup
        Popen = MockPopen()
        Popen.set_command('a command', returncode=3)
        # usage
        process = Popen('a command')
        compare(process.returncode, expected=None)
        # result checking
        compare(process.wait(), expected=3)
        compare(process.returncode, expected=3)
        # test call list
        compare(Popen.all_calls, expected=[
            call.Popen('a command'),
            call.Popen('a command').wait(),
        ])

    def test_send_signal(self):
        # setup
        Popen = MockPopen()
        Popen.set_command('a command')
        # usage
        process = Popen('a command', stdout=PIPE, stderr=PIPE, shell=True)
        process.send_signal(0)
        # result checking
        compare(Popen.all_calls, expected=[
            process.root_call,
            process.root_call.send_signal(0),
        ])

    def test_poll_until_result(self):
        # setup
        Popen = MockPopen()
        Popen.set_command('a command', returncode=3, poll_count=2)
        # example usage
        process = Popen('a command')
        while process.poll() is None:
            # you'd probably have a sleep here, or go off and
            # do some other work.
            pass
        # result checking
        compare(process.returncode, expected=3)
        compare(Popen.all_calls, expected=[
            process.root_call,
            process.root_call.poll(),
            process.root_call.poll(),
            process.root_call.poll(),
        ])

    def test_default_behaviour(self):
        # set up
        self.Popen.set_default(stdout=b'o', stderr=b'e')

        # testing of results
        compare(my_func(), b'o')

        # testing calls were in the right order and with the correct parameters:
        root_call = call.Popen(['svn', 'ls', '-R', 'foo'],
                               stderr=PIPE, stdout=PIPE)
        compare(Popen.all_calls, expected=[
            root_call,
            root_call.communicate()
        ])

    def test_multiple_responses(self):
        # set up
        behaviours = [
            PopenBehaviour(stderr=b'e', returncode=1),
            PopenBehaviour(stdout=b'o'),
        ]

        def behaviour(command, stdin):
            return behaviours.pop(0)

        self.Popen.set_command('svn ls -R foo', behaviour=behaviour)

        # testing of error:
        with ShouldRaise(RuntimeError('something bad happened')):
            my_func()
        # testing of second call:
        compare(my_func(), b'o')

    def test_count_down(self):
        # set up
        self.Popen.set_command('svn ls -R foo', behaviour=CustomBehaviour())
        # testing of error:
        with ShouldRaise(RuntimeError('something bad happened')):
            my_func()
        # testing of second call:
        compare(my_func(), b'o')

    def test_multiple_processes(self):
        # set up
        self.Popen.set_command('process --batch=0', stdout=b'42')
        self.Popen.set_command('process --batch=1', stdout=b'13')

        # testing of results
        compare(process_in_batches(2), expected=55)

        # testing of process management:
        p1 = call.Popen('process --batch=0', shell=True, stderr=PIPE, stdout=PIPE)
        p2 = call.Popen('process --batch=1', shell=True, stderr=PIPE, stdout=PIPE)
        compare(Popen.all_calls, expected=[
            p1,
            p2,
            p1.communicate(),
            p2.communicate(),
        ])

    def test_multiple_processes_unordered(self):
        # set up
        self.Popen.set_command('process --batch=0', stdout=b'42')
        self.Popen.set_command('process --batch=1', stdout=b'13')

        # testing of results
        compare(process_in_batches(2), expected=55)

        # testing of process management:
        p1 = call.Popen('process --batch=0', shell=True, stderr=PIPE, stdout=PIPE)
        p2 = call.Popen('process --batch=1', shell=True, stderr=PIPE, stdout=PIPE)
        compare(Popen.all_calls, expected=SequenceComparison(
            p2,
            p2.communicate(),
            p1,
            p1.communicate(),
            ordered=False
        ))


class CustomBehaviour(object):

    def __init__(self, fail_count=1):
        self.fail_count = fail_count

    def __call__(self, command, stdin):
        while self.fail_count > 0:
            self.fail_count -= 1
            return PopenBehaviour(stderr=b'e', returncode=1)
        return PopenBehaviour(stdout=b'o')


def process_in_batches(n):
    processes = []
    for i in range(n):
        processes.append(Popen('process --batch='+str(i),
                               stdout=PIPE, stderr=PIPE, shell=True))
    total = 0
    for process in processes:
        out, err = process.communicate()
        total += int(out)
    return total
