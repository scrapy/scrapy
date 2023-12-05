# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.python.release} and L{twisted.python._release}.

All of these tests are skipped on platforms other than Linux, as the release is
only ever performed on Linux.
"""
import glob
import operator
import os
import shutil
import sys
import tempfile

from incremental import Version

from twisted.python import release
from twisted.python._release import (
    CheckNewsfragmentScript,
    GitCommand,
    IVCSCommand,
    NotWorkingDirectory,
    Project,
    filePathDelta,
    findTwistedProjects,
    getRepositoryCommand,
    replaceInFile,
    runCommand,
)
from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase

if sys.platform != "win32":
    skip = None
else:
    skip = "Release toolchain only supported on POSIX."

# This should match the GitHub Actions environment used by pre-commit.ci to push changes to the auto-updated branches.
PRECOMMIT_CI_ENVIRON = {
    "GITHUB_HEAD_REF": "pre-commit-ci-update-config",
    "PATH": os.environ["PATH"],
}
# This should match the GHA environment for non pre-commit.ci PRs.
GENERIC_CI_ENVIRON = {
    "GITHUB_HEAD_REF": "1234-some-branch-name",
    "PATH": os.environ["PATH"],
}


class ExternalTempdirTestCase(TestCase):
    """
    A test case which has mkdir make directories outside of the usual spot, so
    that Git commands don't interfere with the Twisted checkout.
    """

    def mktemp(self):
        """
        Make our own directory.
        """
        newDir = tempfile.mkdtemp(dir=tempfile.gettempdir())
        self.addCleanup(shutil.rmtree, newDir)
        return newDir


def _gitConfig(path):
    """
    Set some config in the repo that Git requires to make commits. This isn't
    needed in real usage, just for tests.

    @param path: The path to the Git repository.
    @type path: L{FilePath}
    """
    runCommand(
        [
            "git",
            "config",
            "--file",
            path.child(".git").child("config").path,
            "user.name",
            '"someone"',
        ]
    )
    runCommand(
        [
            "git",
            "config",
            "--file",
            path.child(".git").child("config").path,
            "user.email",
            '"someone@someplace.com"',
        ]
    )


def _gitInit(path):
    """
    Run a git init, and set some config that git requires. This isn't needed in
    real usage.

    @param path: The path to where the Git repo will be created.
    @type path: L{FilePath}
    """
    runCommand(["git", "init", path.path])
    _gitConfig(path)


def genVersion(*args, **kwargs):
    """
    A convenience for generating _version.py data.

    @param args: Arguments to pass to L{Version}.
    @param kwargs: Keyword arguments to pass to L{Version}.
    """
    return "from incremental import Version\n__version__={!r}".format(
        Version(*args, **kwargs)
    )


class StructureAssertingMixin:
    """
    A mixin for L{TestCase} subclasses which provides some methods for
    asserting the structure and contents of directories and files on the
    filesystem.
    """

    def createStructure(self, root, dirDict):
        """
        Create a set of directories and files given a dict defining their
        structure.

        @param root: The directory in which to create the structure.  It must
            already exist.
        @type root: L{FilePath}

        @param dirDict: The dict defining the structure. Keys should be strings
            naming files, values should be strings describing file contents OR
            dicts describing subdirectories.  All files are written in binary
            mode.  Any string values are assumed to describe text files and
            will have their newlines replaced with the platform-native newline
            convention.  For example::

                {"foofile": "foocontents",
                 "bardir": {"barfile": "bar\ncontents"}}
        @type dirDict: C{dict}
        """
        for x in dirDict:
            child = root.child(x)
            if isinstance(dirDict[x], dict):
                child.createDirectory()
                self.createStructure(child, dirDict[x])
            else:
                child.setContent(dirDict[x].replace("\n", os.linesep).encode())

    def assertStructure(self, root, dirDict):
        """
        Assert that a directory is equivalent to one described by a dict.

        @param root: The filesystem directory to compare.
        @type root: L{FilePath}
        @param dirDict: The dict that should describe the contents of the
            directory. It should be the same structure as the C{dirDict}
            parameter to L{createStructure}.
        @type dirDict: C{dict}
        """
        children = [each.basename() for each in root.children()]
        for pathSegment, expectation in dirDict.items():
            child = root.child(pathSegment)
            if callable(expectation):
                self.assertTrue(expectation(child))
            elif isinstance(expectation, dict):
                self.assertTrue(child.isdir(), f"{child.path} is not a dir!")
                self.assertStructure(child, expectation)
            else:
                actual = child.getContent().decode().replace(os.linesep, "\n")
                self.assertEqual(actual, expectation)
            children.remove(pathSegment)
        if children:
            self.fail(f"There were extra children in {root.path}: {children}")


class ProjectTests(ExternalTempdirTestCase):
    """
    There is a first-class representation of a project.
    """

    def assertProjectsEqual(self, observedProjects, expectedProjects):
        """
        Assert that two lists of L{Project}s are equal.
        """
        self.assertEqual(len(observedProjects), len(expectedProjects))
        observedProjects = sorted(
            observedProjects, key=operator.attrgetter("directory")
        )
        expectedProjects = sorted(
            expectedProjects, key=operator.attrgetter("directory")
        )
        for observed, expected in zip(observedProjects, expectedProjects):
            self.assertEqual(observed.directory, expected.directory)

    def makeProject(self, version, baseDirectory=None):
        """
        Make a Twisted-style project in the given base directory.

        @param baseDirectory: The directory to create files in
            (as a L{FilePath).
        @param version: The version information for the project.
        @return: L{Project} pointing to the created project.
        """
        if baseDirectory is None:
            baseDirectory = FilePath(self.mktemp())
        segments = version[0].split(".")
        directory = baseDirectory
        for segment in segments:
            directory = directory.child(segment)
            if not directory.exists():
                directory.createDirectory()
            directory.child("__init__.py").setContent(b"")
        directory.child("newsfragments").createDirectory()
        directory.child("_version.py").setContent(genVersion(*version).encode())
        return Project(directory)

    def makeProjects(self, *versions):
        """
        Create a series of projects underneath a temporary base directory.

        @return: A L{FilePath} for the base directory.
        """
        baseDirectory = FilePath(self.mktemp())
        for version in versions:
            self.makeProject(version, baseDirectory)
        return baseDirectory

    def test_getVersion(self):
        """
        Project objects know their version.
        """
        version = ("twisted", 2, 1, 0)
        project = self.makeProject(version)
        self.assertEqual(project.getVersion(), Version(*version))

    def test_repr(self):
        """
        The representation of a Project is Project(directory).
        """
        foo = Project(FilePath("bar"))
        self.assertEqual(repr(foo), "Project(%r)" % (foo.directory))

    def test_findTwistedStyleProjects(self):
        """
        findTwistedStyleProjects finds all projects underneath a particular
        directory. A 'project' is defined by the existence of a 'newsfragments'
        directory and is returned as a Project object.
        """
        baseDirectory = self.makeProjects(("foo", 2, 3, 0), ("foo.bar", 0, 7, 4))
        projects = findTwistedProjects(baseDirectory)
        self.assertProjectsEqual(
            projects,
            [
                Project(baseDirectory.child("foo")),
                Project(baseDirectory.child("foo").child("bar")),
            ],
        )


class UtilityTests(ExternalTempdirTestCase):
    """
    Tests for various utility functions for releasing.
    """

    def test_chdir(self):
        """
        Test that the runChdirSafe is actually safe, i.e., it still
        changes back to the original directory even if an error is
        raised.
        """
        cwd = os.getcwd()

        def chAndBreak():
            os.mkdir("releaseCh")
            os.chdir("releaseCh")
            1 // 0

        self.assertRaises(ZeroDivisionError, release.runChdirSafe, chAndBreak)
        self.assertEqual(cwd, os.getcwd())

    def test_replaceInFile(self):
        """
        L{replaceInFile} replaces data in a file based on a dict. A key from
        the dict that is found in the file is replaced with the corresponding
        value.
        """
        content = "foo\nhey hey $VER\nbar\n"
        with open("release.replace", "w") as outf:
            outf.write(content)

        expected = content.replace("$VER", "2.0.0")
        replaceInFile("release.replace", {"$VER": "2.0.0"})
        with open("release.replace") as f:
            self.assertEqual(f.read(), expected)

        expected = expected.replace("2.0.0", "3.0.0")
        replaceInFile("release.replace", {"2.0.0": "3.0.0"})
        with open("release.replace") as f:
            self.assertEqual(f.read(), expected)


class FilePathDeltaTests(TestCase):
    """
    Tests for L{filePathDelta}.
    """

    def test_filePathDeltaSubdir(self):
        """
        L{filePathDelta} can create a simple relative path to a child path.
        """
        self.assertEqual(
            filePathDelta(FilePath("/foo/bar"), FilePath("/foo/bar/baz")), ["baz"]
        )

    def test_filePathDeltaSiblingDir(self):
        """
        L{filePathDelta} can traverse upwards to create relative paths to
        siblings.
        """
        self.assertEqual(
            filePathDelta(FilePath("/foo/bar"), FilePath("/foo/baz")), ["..", "baz"]
        )

    def test_filePathNoCommonElements(self):
        """
        L{filePathDelta} can create relative paths to totally unrelated paths
        for maximum portability.
        """
        self.assertEqual(
            filePathDelta(FilePath("/foo/bar"), FilePath("/baz/quux")),
            ["..", "..", "baz", "quux"],
        )

    def test_filePathDeltaSimilarEndElements(self):
        """
        L{filePathDelta} doesn't take into account final elements when
        comparing 2 paths, but stops at the first difference.
        """
        self.assertEqual(
            filePathDelta(FilePath("/foo/bar/bar/spam"), FilePath("/foo/bar/baz/spam")),
            ["..", "..", "baz", "spam"],
        )


class CommandsTestMixin(StructureAssertingMixin):
    """
    Test mixin for the VCS commands used by the release scripts.
    """

    def setUp(self):
        self.tmpDir = FilePath(self.mktemp())

    def test_ensureIsWorkingDirectoryWithWorkingDirectory(self):
        """
        Calling the C{ensureIsWorkingDirectory} VCS command's method on a valid
        working directory doesn't produce any error.
        """
        reposDir = self.makeRepository(self.tmpDir)
        self.assertIsNone(self.createCommand.ensureIsWorkingDirectory(reposDir))

    def test_ensureIsWorkingDirectoryWithNonWorkingDirectory(self):
        """
        Calling the C{ensureIsWorkingDirectory} VCS command's method on an
        invalid working directory raises a L{NotWorkingDirectory} exception.
        """
        self.assertRaises(
            NotWorkingDirectory,
            self.createCommand.ensureIsWorkingDirectory,
            self.tmpDir,
        )

    def test_statusClean(self):
        """
        Calling the C{isStatusClean} VCS command's method on a repository with
        no pending modifications returns C{True}.
        """
        reposDir = self.makeRepository(self.tmpDir)
        self.assertTrue(self.createCommand.isStatusClean(reposDir))

    def test_statusNotClean(self):
        """
        Calling the C{isStatusClean} VCS command's method on a repository with
        no pending modifications returns C{False}.
        """
        reposDir = self.makeRepository(self.tmpDir)
        reposDir.child("some-file").setContent(b"something")
        self.assertFalse(self.createCommand.isStatusClean(reposDir))

    def test_remove(self):
        """
        Calling the C{remove} VCS command's method remove the specified path
        from the directory.
        """
        reposDir = self.makeRepository(self.tmpDir)
        testFile = reposDir.child("some-file")
        testFile.setContent(b"something")
        self.commitRepository(reposDir)
        self.assertTrue(testFile.exists())

        self.createCommand.remove(testFile)
        testFile.restat(False)  # Refresh the file information
        self.assertFalse(testFile.exists(), "File still exists")

    def test_export(self):
        """
        The C{exportTo} VCS command's method export the content of the
        repository as identical in a specified directory.
        """
        structure = {
            "README.rst": "Hi this is 1.0.0.",
            "twisted": {
                "newsfragments": {"README": "Hi this is 1.0.0"},
                "_version.py": genVersion("twisted", 1, 0, 0),
                "web": {
                    "newsfragments": {"README": "Hi this is 1.0.0"},
                    "_version.py": genVersion("twisted.web", 1, 0, 0),
                },
            },
        }
        reposDir = self.makeRepository(self.tmpDir)
        self.createStructure(reposDir, structure)
        self.commitRepository(reposDir)

        exportDir = FilePath(self.mktemp()).child("export")
        self.createCommand.exportTo(reposDir, exportDir)
        self.assertStructure(exportDir, structure)


class GitCommandTest(CommandsTestMixin, ExternalTempdirTestCase):
    """
    Specific L{CommandsTestMixin} related to Git repositories through
    L{GitCommand}.
    """

    createCommand = GitCommand

    def makeRepository(self, root):
        """
        Create a Git repository in the specified path.

        @type root: L{FilePath}
        @params root: The directory to create the Git repository into.

        @return: The path to the repository just created.
        @rtype: L{FilePath}
        """
        _gitInit(root)
        return root

    def commitRepository(self, repository):
        """
        Add and commit all the files from the Git repository specified.

        @type repository: L{FilePath}
        @params repository: The Git repository to commit into.
        """
        runCommand(
            ["git", "-C", repository.path, "add"] + glob.glob(repository.path + "/*")
        )
        runCommand(["git", "-C", repository.path, "commit", "-m", "hop"])


class RepositoryCommandDetectionTest(ExternalTempdirTestCase):
    """
    Test the L{getRepositoryCommand} to access the right set of VCS commands
    depending on the repository manipulated.
    """

    def setUp(self):
        self.repos = FilePath(self.mktemp())

    def test_git(self):
        """
        L{getRepositoryCommand} from a Git repository returns L{GitCommand}.
        """
        _gitInit(self.repos)
        cmd = getRepositoryCommand(self.repos)
        self.assertIs(cmd, GitCommand)

    def test_unknownRepository(self):
        """
        L{getRepositoryCommand} from a directory which doesn't look like a Git
        repository produces a L{NotWorkingDirectory} exception.
        """
        self.assertRaises(NotWorkingDirectory, getRepositoryCommand, self.repos)


class VCSCommandInterfaceTests(TestCase):
    """
    Test that the VCS command classes implement their interface.
    """

    def test_git(self):
        """
        L{GitCommand} implements L{IVCSCommand}.
        """
        self.assertTrue(IVCSCommand.implementedBy(GitCommand))


class CheckNewsfragmentScriptTests(ExternalTempdirTestCase):
    """
    L{CheckNewsfragmentScript}.
    """

    def setUp(self):
        self.origin = FilePath(self.mktemp())
        _gitInit(self.origin)
        runCommand(["git", "checkout", "-b", "trunk"], cwd=self.origin.path)
        self.origin.child("test").setContent(b"test!")
        runCommand(["git", "add", self.origin.child("test").path], cwd=self.origin.path)
        runCommand(["git", "commit", "-m", "initial"], cwd=self.origin.path)

        self.repo = FilePath(self.mktemp())

        runCommand(["git", "clone", self.origin.path, self.repo.path])
        _gitConfig(self.repo)
        # Inject a rigged environment to have full control over the test execution.
        self.patch(os, "environ", GENERIC_CI_ENVIRON)

    def test_noArgs(self):
        """
        Too few arguments returns a failure.
        """
        logs = []

        with self.assertRaises(SystemExit) as e:
            CheckNewsfragmentScript(logs.append).main([])

        self.assertEqual(
            e.exception.args, ("Must specify one argument: the Twisted checkout",)
        )

    def test_diffFromTrunkNoNewsfragments(self):
        """
        If there are changes from trunk, then there should also be a
        newsfragment.
        """
        runCommand(["git", "checkout", "-b", "mypatch"], cwd=self.repo.path)
        somefile = self.repo.child("somefile")
        somefile.setContent(b"change")

        runCommand(["git", "add", somefile.path, somefile.path], cwd=self.repo.path)
        runCommand(["git", "commit", "-m", "some file"], cwd=self.repo.path)

        logs = []

        with self.assertRaises(SystemExit) as e:
            CheckNewsfragmentScript(logs.append).main([self.repo.path])

        self.assertEqual(e.exception.args, (1,))
        self.assertEqual(logs[-1], "No newsfragment found. Have you committed it?")

    def test_noChangeFromTrunk(self):
        """
        If there are no changes from trunk, then no need to check the
        newsfragments
        """
        runCommand(["git", "checkout", "-b", "mypatch"], cwd=self.repo.path)

        logs = []

        with self.assertRaises(SystemExit) as e:
            CheckNewsfragmentScript(logs.append).main([self.repo.path])

        self.assertEqual(e.exception.args, (0,))
        self.assertEqual(
            logs[-1], "On trunk or no diffs from trunk; no need to look at this."
        )

    def test_trunk(self):
        """
        Running it on trunk always gives green.
        """
        logs = []

        with self.assertRaises(SystemExit) as e:
            CheckNewsfragmentScript(logs.append).main([self.repo.path])

        self.assertEqual(e.exception.args, (0,))
        self.assertEqual(
            logs[-1], "On trunk or no diffs from trunk; no need to look at this."
        )

    def test_release(self):
        """
        Running it on a release branch returns green if there is no
        newsfragments even if there are changes.
        """
        runCommand(
            ["git", "checkout", "-b", "release-16.11111-9001"], cwd=self.repo.path
        )

        somefile = self.repo.child("somefile")
        somefile.setContent(b"change")

        runCommand(["git", "add", somefile.path, somefile.path], cwd=self.repo.path)
        runCommand(["git", "commit", "-m", "some file"], cwd=self.repo.path)

        logs = []

        with self.assertRaises(SystemExit) as e:
            CheckNewsfragmentScript(logs.append).main([self.repo.path])

        self.assertEqual(e.exception.args, (0,))
        self.assertEqual(logs[-1], "Release branch with no newsfragments, all good.")

    def test_releaseWithNewsfragments(self):
        """
        Running it on a release branch returns red if there are new
        newsfragments.
        """
        runCommand(
            ["git", "checkout", "-b", "release-16.11111-9001"], cwd=self.repo.path
        )

        newsfragments = self.repo.child("twisted").child("newsfragments")
        newsfragments.makedirs()
        fragment = newsfragments.child("1234.misc")
        fragment.setContent(b"")

        unrelated = self.repo.child("somefile")
        unrelated.setContent(b"Boo")

        runCommand(["git", "add", fragment.path, unrelated.path], cwd=self.repo.path)
        runCommand(["git", "commit", "-m", "fragment"], cwd=self.repo.path)

        logs = []

        with self.assertRaises(SystemExit) as e:
            CheckNewsfragmentScript(logs.append).main([self.repo.path])

        self.assertEqual(e.exception.args, (1,))
        self.assertEqual(logs[-1], "No newsfragments should be on the release branch.")

    def test_preCommitAutoupdate(self):
        """
        Running it on the autoupdate branch returns green if there is no
        newsfragments even if there are changes.
        """
        runCommand(
            ["git", "checkout", "-b", "pre-commit-ci-update-config"], cwd=self.repo.path
        )

        somefile = self.repo.child("somefile")
        somefile.setContent(b"change")

        runCommand(["git", "add", somefile.path, somefile.path], cwd=self.repo.path)
        runCommand(["git", "commit", "-m", "some file"], cwd=self.repo.path)

        logs = []
        self.patch(os, "environ", PRECOMMIT_CI_ENVIRON)

        with self.assertRaises(SystemExit) as e:
            CheckNewsfragmentScript(logs.append).main([self.repo.path])

        self.assertEqual(e.exception.args, (0,))
        self.assertEqual(
            logs[-1], "Autoupdated branch with no newsfragments, all good."
        )

    def test_preCommitAutoupdateWithNewsfragments(self):
        """
        Running it on the autoupdate branch returns red if there are new
        newsfragments.
        """
        runCommand(
            ["git", "checkout", "-b", "pre-commit-ci-update-config"], cwd=self.repo.path
        )

        newsfragments = self.repo.child("twisted").child("newsfragments")
        newsfragments.makedirs()
        fragment = newsfragments.child("1234.misc")
        fragment.setContent(b"")

        unrelated = self.repo.child("somefile")
        unrelated.setContent(b"Boo")

        runCommand(["git", "add", fragment.path, unrelated.path], cwd=self.repo.path)
        runCommand(["git", "commit", "-m", "fragment"], cwd=self.repo.path)

        logs = []
        self.patch(os, "environ", PRECOMMIT_CI_ENVIRON)

        with self.assertRaises(SystemExit) as e:
            CheckNewsfragmentScript(logs.append).main([self.repo.path])

        self.assertEqual(e.exception.args, (1,))
        self.assertEqual(
            logs[-1], "No newsfragments should be present on an autoupdated branch."
        )

    def test_onlyQuotes(self):
        """
        Running it on a branch with only a quotefile change gives green.
        """
        runCommand(["git", "checkout", "-b", "quotefile"], cwd=self.repo.path)

        fun = self.repo.child("docs").child("fun")
        fun.makedirs()
        quotes = fun.child("Twisted.Quotes")
        quotes.setContent(b"Beep boop")

        runCommand(["git", "add", quotes.path], cwd=self.repo.path)
        runCommand(["git", "commit", "-m", "quotes"], cwd=self.repo.path)

        logs = []

        with self.assertRaises(SystemExit) as e:
            CheckNewsfragmentScript(logs.append).main([self.repo.path])

        self.assertEqual(e.exception.args, (0,))
        self.assertEqual(logs[-1], "Quotes change only; no newsfragment needed.")

    def test_newsfragmentAdded(self):
        """
        Running it on a branch with a fragment in the newsfragments dir added
        returns green.
        """
        runCommand(["git", "checkout", "-b", "quotefile"], cwd=self.repo.path)

        newsfragments = self.repo.child("twisted").child("newsfragments")
        newsfragments.makedirs()
        fragment = newsfragments.child("1234.misc")
        fragment.setContent(b"")

        unrelated = self.repo.child("somefile")
        unrelated.setContent(b"Boo")

        runCommand(["git", "add", fragment.path, unrelated.path], cwd=self.repo.path)
        runCommand(["git", "commit", "-m", "newsfragment"], cwd=self.repo.path)

        logs = []

        with self.assertRaises(SystemExit) as e:
            CheckNewsfragmentScript(logs.append).main([self.repo.path])

        self.assertEqual(e.exception.args, (0,))
        self.assertEqual(logs[-1], "Found twisted/newsfragments/1234.misc")

    def test_topfileButNotFragmentAdded(self):
        """
        Running it on a branch with a non-fragment in the topfiles dir does not
        return green.
        """
        runCommand(["git", "checkout", "-b", "quotefile"], cwd=self.repo.path)

        topfiles = self.repo.child("twisted").child("topfiles")
        topfiles.makedirs()
        notFragment = topfiles.child("1234.txt")
        notFragment.setContent(b"")

        unrelated = self.repo.child("somefile")
        unrelated.setContent(b"Boo")

        runCommand(["git", "add", notFragment.path, unrelated.path], cwd=self.repo.path)
        runCommand(["git", "commit", "-m", "not topfile"], cwd=self.repo.path)

        logs = []

        with self.assertRaises(SystemExit) as e:
            CheckNewsfragmentScript(logs.append).main([self.repo.path])

        self.assertEqual(e.exception.args, (1,))
        self.assertEqual(logs[-1], "No newsfragment found. Have you committed it?")

    def test_newsfragmentAddedButWithOtherNewsfragments(self):
        """
        Running it on a branch with a fragment in the topfiles dir added
        returns green, even if there are other files in the topfiles dir.
        """
        runCommand(["git", "checkout", "-b", "quotefile"], cwd=self.repo.path)

        newsfragments = self.repo.child("twisted").child("newsfragments")
        newsfragments.makedirs()
        fragment = newsfragments.child("1234.misc")
        fragment.setContent(b"")

        unrelated = newsfragments.child("somefile")
        unrelated.setContent(b"Boo")

        runCommand(["git", "add", fragment.path, unrelated.path], cwd=self.repo.path)
        runCommand(["git", "commit", "-m", "newsfragment"], cwd=self.repo.path)

        logs = []

        with self.assertRaises(SystemExit) as e:
            CheckNewsfragmentScript(logs.append).main([self.repo.path])

        self.assertEqual(e.exception.args, (0,))
        self.assertEqual(logs[-1], "Found twisted/newsfragments/1234.misc")
