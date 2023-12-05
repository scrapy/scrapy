# -*- test-case-name: twisted.python.test.test_release -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Twisted's automated release system.

This module is only for use within Twisted's release system. If you are anyone
else, do not use it. The interface and behaviour will change without notice.

Only Linux is supported by this code.  It should not be used by any tools
which must run on multiple platforms (eg the setup.py script).
"""

import os
import sys
from subprocess import STDOUT, CalledProcessError, check_output
from typing import Dict

from zope.interface import Interface, implementer

from twisted.python.compat import execfile

# Types of newsfragments.
NEWSFRAGMENT_TYPES = ["doc", "bugfix", "misc", "feature", "removal"]


def runCommand(args, **kwargs):
    """Execute a vector of arguments.

    This is a wrapper around L{subprocess.check_output}, so it takes
    the same arguments as L{subprocess.Popen} with one difference: all
    arguments after the vector must be keyword arguments.

    @param args: arguments passed to L{subprocess.check_output}
    @param kwargs: keyword arguments passed to L{subprocess.check_output}
    @return: command output
    @rtype: L{bytes}
    """
    kwargs["stderr"] = STDOUT
    return check_output(args, **kwargs)


class IVCSCommand(Interface):
    """
    An interface for VCS commands.
    """

    def ensureIsWorkingDirectory(path):
        """
        Ensure that C{path} is a working directory of this VCS.

        @type path: L{twisted.python.filepath.FilePath}
        @param path: The path to check.
        """

    def isStatusClean(path):
        """
        Return the Git status of the files in the specified path.

        @type path: L{twisted.python.filepath.FilePath}
        @param path: The path to get the status from (can be a directory or a
            file.)
        """

    def remove(path):
        """
        Remove the specified path from a the VCS.

        @type path: L{twisted.python.filepath.FilePath}
        @param path: The path to remove from the repository.
        """

    def exportTo(fromDir, exportDir):
        """
        Export the content of the VCSrepository to the specified directory.

        @type fromDir: L{twisted.python.filepath.FilePath}
        @param fromDir: The path to the VCS repository to export.

        @type exportDir: L{twisted.python.filepath.FilePath}
        @param exportDir: The directory to export the content of the
            repository to. This directory doesn't have to exist prior to
            exporting the repository.
        """


@implementer(IVCSCommand)
class GitCommand:
    """
    Subset of Git commands to release Twisted from a Git repository.
    """

    @staticmethod
    def ensureIsWorkingDirectory(path):
        """
        Ensure that C{path} is a Git working directory.

        @type path: L{twisted.python.filepath.FilePath}
        @param path: The path to check.
        """
        try:
            runCommand(["git", "rev-parse"], cwd=path.path)
        except (CalledProcessError, OSError):
            raise NotWorkingDirectory(
                f"{path.path} does not appear to be a Git repository."
            )

    @staticmethod
    def isStatusClean(path):
        """
        Return the Git status of the files in the specified path.

        @type path: L{twisted.python.filepath.FilePath}
        @param path: The path to get the status from (can be a directory or a
            file.)
        """
        status = runCommand(["git", "-C", path.path, "status", "--short"]).strip()
        return status == b""

    @staticmethod
    def remove(path):
        """
        Remove the specified path from a Git repository.

        @type path: L{twisted.python.filepath.FilePath}
        @param path: The path to remove from the repository.
        """
        runCommand(["git", "-C", path.dirname(), "rm", path.path])

    @staticmethod
    def exportTo(fromDir, exportDir):
        """
        Export the content of a Git repository to the specified directory.

        @type fromDir: L{twisted.python.filepath.FilePath}
        @param fromDir: The path to the Git repository to export.

        @type exportDir: L{twisted.python.filepath.FilePath}
        @param exportDir: The directory to export the content of the
            repository to. This directory doesn't have to exist prior to
            exporting the repository.
        """
        runCommand(
            [
                "git",
                "-C",
                fromDir.path,
                "checkout-index",
                "--all",
                "--force",
                # prefix has to end up with a "/" so that files get copied
                # to a directory whose name is the prefix.
                "--prefix",
                exportDir.path + "/",
            ]
        )


def getRepositoryCommand(directory):
    """
    Detect the VCS used in the specified directory and return a L{GitCommand}
    if the directory is a Git repository. If the directory is not git, it
    raises a L{NotWorkingDirectory} exception.

    @type directory: L{FilePath}
    @param directory: The directory to detect the VCS used from.

    @rtype: L{GitCommand}

    @raise NotWorkingDirectory: if no supported VCS can be found from the
        specified directory.
    """
    try:
        GitCommand.ensureIsWorkingDirectory(directory)
        return GitCommand
    except (NotWorkingDirectory, OSError):
        # It's not Git, but that's okay, eat the error
        pass

    raise NotWorkingDirectory(f"No supported VCS can be found in {directory.path}")


class Project:
    """
    A representation of a project that has a version.

    @ivar directory: A L{twisted.python.filepath.FilePath} pointing to the base
        directory of a Twisted-style Python package. The package should contain
        a C{_version.py} file and a C{newsfragments} directory that contains a
        C{README} file.
    """

    def __init__(self, directory):
        self.directory = directory

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.directory!r})"

    def getVersion(self):
        """
        @return: A L{incremental.Version} specifying the version number of the
            project based on live python modules.
        """
        namespace: Dict[str, object] = {}
        directory = self.directory
        while not namespace:
            if directory.path == "/":
                raise Exception("Not inside a Twisted project.")
            elif not directory.basename() == "twisted":
                directory = directory.parent()
            else:
                execfile(directory.child("_version.py").path, namespace)
        return namespace["__version__"]


def findTwistedProjects(baseDirectory):
    """
    Find all Twisted-style projects beneath a base directory.

    @param baseDirectory: A L{twisted.python.filepath.FilePath} to look inside.
    @return: A list of L{Project}.
    """
    projects = []
    for filePath in baseDirectory.walk():
        if filePath.basename() == "newsfragments":
            projectDirectory = filePath.parent()
            projects.append(Project(projectDirectory))
    return projects


def replaceInFile(filename, oldToNew):
    """
    I replace the text `oldstr' with `newstr' in `filename' using science.
    """
    os.rename(filename, filename + ".bak")
    with open(filename + ".bak") as f:
        d = f.read()
    for k, v in oldToNew.items():
        d = d.replace(k, v)
    with open(filename + ".new", "w") as f:
        f.write(d)
    os.rename(filename + ".new", filename)
    os.unlink(filename + ".bak")


class NoDocumentsFound(Exception):
    """
    Raised when no input documents are found.
    """


def filePathDelta(origin, destination):
    """
    Return a list of strings that represent C{destination} as a path relative
    to C{origin}.

    It is assumed that both paths represent directories, not files. That is to
    say, the delta of L{twisted.python.filepath.FilePath} /foo/bar to
    L{twisted.python.filepath.FilePath} /foo/baz will be C{../baz},
    not C{baz}.

    @type origin: L{twisted.python.filepath.FilePath}
    @param origin: The origin of the relative path.

    @type destination: L{twisted.python.filepath.FilePath}
    @param destination: The destination of the relative path.
    """
    commonItems = 0
    path1 = origin.path.split(os.sep)
    path2 = destination.path.split(os.sep)
    for elem1, elem2 in zip(path1, path2):
        if elem1 == elem2:
            commonItems += 1
        else:
            break
    path = [".."] * (len(path1) - commonItems)
    return path + path2[commonItems:]


class NotWorkingDirectory(Exception):
    """
    Raised when a directory does not appear to be a repository directory of a
    supported VCS.
    """


class CheckNewsfragmentScript:
    """
    A thing for checking whether a checkout has a newsfragment.
    """

    def __init__(self, _print):
        self._print = _print

    def main(self, args):
        """
        Run the script.

        @type args: L{list} of L{str}
        @param args: The command line arguments to process. This must contain
            one string: the path to the root of the Twisted checkout.
        """
        if len(args) != 1:
            sys.exit("Must specify one argument: the Twisted checkout")

        encoding = sys.stdout.encoding or "ascii"
        location = os.path.abspath(args[0])

        branch = (
            runCommand([b"git", b"rev-parse", b"--abbrev-ref", "HEAD"], cwd=location)
            .decode(encoding)
            .strip()
        )

        # diff-filter=d to exclude deleted newsfiles (which will happen on the
        # release branch)
        r = (
            runCommand(
                [
                    b"git",
                    b"diff",
                    b"--name-only",
                    b"origin/trunk...",
                    b"--diff-filter=d",
                ],
                cwd=location,
            )
            .decode(encoding)
            .strip()
        )

        if not r:
            self._print("On trunk or no diffs from trunk; no need to look at this.")
            sys.exit(0)

        files = r.strip().split(os.linesep)

        self._print("Looking at these files:")
        for change in files:
            self._print(change)
        self._print("----")

        if len(files) == 1:
            if files[0] == os.sep.join(["docs", "fun", "Twisted.Quotes"]):
                self._print("Quotes change only; no newsfragment needed.")
                sys.exit(0)

        newsfragments = []

        for change in files:
            if os.sep + "newsfragments" + os.sep in change:
                if "." in change and change.rsplit(".", 1)[1] in NEWSFRAGMENT_TYPES:
                    newsfragments.append(change)

        if branch.startswith("release-"):
            if newsfragments:
                self._print("No newsfragments should be on the release branch.")
                sys.exit(1)
            else:
                self._print("Release branch with no newsfragments, all good.")
                sys.exit(0)

        if os.environ.get("GITHUB_HEAD_REF", "") == "pre-commit-ci-update-config":
            # The run was triggered by pre-commit.ci.
            if newsfragments:
                self._print(
                    "No newsfragments should be present on an autoupdated branch."
                )
                sys.exit(1)
            else:
                self._print("Autoupdated branch with no newsfragments, all good.")
                sys.exit(0)

        for change in newsfragments:
            self._print("Found " + change)
            sys.exit(0)

        self._print("No newsfragment found. Have you committed it?")
        sys.exit(1)
