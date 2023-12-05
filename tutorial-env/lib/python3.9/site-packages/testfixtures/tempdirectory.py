import atexit
import os
import warnings
from pathlib import Path

from re import compile
from tempfile import mkdtemp
from typing import Union, Sequence, TYPE_CHECKING, Tuple, Callable

from testfixtures.comparison import compare
from testfixtures.utils import wrap

from .rmtree import rmtree


PathStrings = Union[str, Tuple[str]]


if TYPE_CHECKING:
    import py.path


class TempDirectory:
    """
    A class representing a temporary directory on disk.

    :param ignore: A sequence of strings containing regular expression
                   patterns that match filenames that should be
                   ignored by the :class:`TempDirectory` listing and
                   checking methods.

    :param create: If `True`, the temporary directory will be created
                   as part of class instantiation.

    :param path: If passed, this should be a string containing an
                 absolute path to use as the temporary directory. When
                 passed, :class:`TempDirectory` will not create a new
                 directory to use.

    :param encoding: A default encoding to use for :meth:`read` and
                     :meth:`write` operations when the ``encoding`` parameter
                     is not passed to those methods.
    """

    instances = set()
    atexit_setup = False

    #: The absolute path of the :class:`TempDirectory` on disk
    path = None

    def __init__(
            self,
            path: Union[str, Path, 'py.path.local'] = None,
            *,
            ignore: Sequence[str] = (),
            create: bool = None,
            encoding: str = None
    ):
        self.ignore = []
        for regex in ignore:
            self.ignore.append(compile(regex))
        self.path = str(path) if path else None
        self.encoding = encoding
        self.dont_remove = bool(path)
        if create or (path is None and create is None):
            self.create()

    @classmethod
    def atexit(cls):
        if cls.instances:
            warnings.warn(
                'TempDirectory instances not cleaned up by shutdown:\n'
                '%s' % ('\n'.join(i.path for i in cls.instances))
                )

    def create(self) -> 'TempDirectory':
        """
        Create a temporary directory for this instance to use if one
        has not already been created.
        """
        if self.path:
            return self
        self.path = mkdtemp()
        self.instances.add(self)
        if not self.__class__.atexit_setup:
            atexit.register(self.atexit)
            self.__class__.atexit_setup = True
        return self

    def cleanup(self) -> None:
        """
        Delete the temporary directory and anything in it.
        This :class:`TempDirectory` cannot be used again unless
        :meth:`create` is called.
        """
        if self.path and os.path.exists(self.path) and not self.dont_remove:
            rmtree(self.path)
            del self.path
        if self in self.instances:
            self.instances.remove(self)

    @classmethod
    def cleanup_all(cls) -> None:
        """
        Delete all temporary directories associated with all
        :class:`TempDirectory` objects.
        """
        for i in tuple(cls.instances):
            i.cleanup()

    def actual(
            self,
            path: PathStrings = None,
            recursive: bool = False,
            files_only: bool = False,
            followlinks: bool = False,
    ):
        path = self._join(path) if path else self.path

        result = []
        if recursive:
            for dirpath, dirnames, filenames in os.walk(
                    path, followlinks=followlinks
            ):
                dirpath = '/'.join(dirpath[len(path)+1:].split(os.sep))
                if dirpath:
                    dirpath += '/'

                for dirname in dirnames:
                    if not files_only:
                        result.append(dirpath+dirname+'/')

                for name in sorted(filenames):
                    result.append(dirpath+name)
        else:
            for n in os.listdir(path):
                result.append(n)

        filtered = []
        for path in sorted(result):
            ignore = False
            for regex in self.ignore:
                if regex.search(path):
                    ignore = True
                    break
            if ignore:
                continue
            filtered.append(path)
        return filtered

    def listdir(self, path: PathStrings = None, recursive: bool = False):
        """
        Print the contents of the specified directory.

        :param path: The path to list, which can be:

                     * `None`, indicating the root of the temporary
                       directory should be listed.

                     * A tuple of strings, indicating that the
                       elements of the tuple should be used as directory
                       names to traverse from the root of the
                       temporary directory to find the directory to be
                       listed.

                     * A forward-slash separated string, indicating
                       the directory or subdirectory that should be
                       traversed to from the temporary directory and
                       listed.

        :param recursive: If `True`, the directory specified will have
                          its subdirectories recursively listed too.
        """
        actual = self.actual(path, recursive)
        if not actual:
            print('No files or directories found.')
        for n in actual:
            print(n)

    def compare(
            self,
            expected: Sequence[str],
            path: PathStrings = None,
            files_only: bool = False,
            recursive: bool = True,
            followlinks: bool = False,
    ):
        """
        Compare the expected contents with the actual contents of the temporary
        directory. An :class:`AssertionError` will be raised if they are not the
        same.

        :param expected: A sequence of strings containing the paths
                         expected in the directory. These paths should
                         be forward-slash separated and relative to
                         the root of the temporary directory.

        :param path: The path to use as the root for the comparison,
                     relative to the root of the temporary directory.
                     This can either be:

                     * A tuple of strings, making up the relative path.

                     * A forward-slash separated string.

                     If it is not provided, the root of the temporary
                     directory will be used.

        :param files_only: If specified, directories will be excluded from
                           the list of actual paths used in the comparison.

        :param recursive: If ``False``, only the direct contents of
                          the directory specified by ``path`` will be included
                          in the actual contents used for comparison.

        :param followlinks: If ``True``, symlinks and hard links
                            will be followed when recursively building up
                            the actual list of directory contents.
        """

        __tracebackhide__ = True
    
        compare(expected=sorted(expected),
                actual=tuple(self.actual(
                    path, recursive, files_only, followlinks
                )),
                recursive=False)

    def _join(self, name):
        # make things platform independent
        if isinstance(name, str):
            name = name.split('/')
        relative = os.sep.join(name).rstrip(os.sep)
        if relative.startswith(os.sep):
            if relative.startswith(self.path):
                return relative
            raise ValueError(
                'Attempt to read or write outside the temporary Directory'
                )
        return os.path.join(self.path, relative)

    def makedir(self, dirpath: PathStrings):
        """
        Make an empty directory at the specified path within the
        temporary directory. Any intermediate subdirectories that do
        not exist will also be created.

        :param dirpath: The directory to create, which can be:

                        * A tuple of strings.

                        * A forward-slash separated string.

        :returns: The absolute path of the created directory.
        """
        thepath = self._join(dirpath)
        os.makedirs(thepath)
        return thepath

    def write(self, filepath: PathStrings, data: Union[bytes, str], encoding: str = None):
        """
        Write the supplied data to a file at the specified path within
        the temporary directory. Any subdirectories specified that do
        not exist will also be created.

        The file will always be written in binary mode. The data supplied must
        either be bytes or an encoding must be supplied to convert the string
        into bytes.

        :param filepath: The path to the file to create, which can be:

                         * A tuple of strings.

                         * A forward-slash separated string.

        :param data:

          :class:`bytes` containing the data to be written, or a :class:`str`
          if ``encoding`` has been supplied.

        :param encoding: The encoding to be used if data is not bytes. Should
                         not be passed if data is already bytes.

        :returns: The absolute path of the file written.
        """
        if isinstance(filepath, str):
            filepath = filepath.split('/')
        if len(filepath) > 1:
            dirpath = self._join(filepath[:-1])
            if not os.path.exists(dirpath):
                os.makedirs(dirpath)
        thepath = self._join(filepath)
        encoding = encoding or self.encoding
        if encoding is not None:
            data = data.encode(encoding)
        with open(thepath, 'wb') as f:
            f.write(data)
        return thepath

    def as_string(self, path: Union[str, Sequence[str]] = None) -> str:
        """
        Return the full path on disk that corresponds to the path
        relative to the temporary directory that is passed in.

        :param path: The path to the file to create, which can be:

                     * A tuple of strings.

                     * A forward-slash separated string.

        :returns: A string containing the absolute path.

        """
        return self.path if path is None else self._join(path)

    #: .. deprecated:: 7
    #:
    #:   Use :meth:`as_string` instead.
    getpath = as_string

    def as_path(self, path: PathStrings = None) -> Path:
        """
        Return the :class:`~pathlib.Path` that corresponds to the path
        relative to the temporary directory that is passed in.

        :param path: The path to the file to create, which can be:

                     * A tuple of strings.

                     * A forward-slash separated string.
        """
        return Path(self.path if path is None else self._join(path))

    def as_local(self, path: PathStrings = None) -> 'py.path.local':
        """
        Return the :class:`py.path.local` that corresponds to the path
        relative to the temporary directory that is passed in.

        :param path: The path to the file to create, which can be:

                     * A tuple of strings.

                     * A forward-slash separated string.
        """
        from py.path import local
        return local(self.path if path is None else self._join(path))

    def read(self, filepath: PathStrings, encoding: str = None) -> Union[bytes, str]:
        """
        Reads the file at the specified path within the temporary
        directory.

        The file is always read in binary mode. Bytes will be returned unless
        an encoding is supplied, in which case a unicode string of the decoded
        data will be returned.

        :param filepath: The path to the file to read, which can be:

                         * A tuple of strings.

                         * A forward-slash separated string.

        :param encoding: The encoding used to decode the data in the file.

        :returns:

          The contents of the file as a :class:`str` or :class:`bytes`, if ``encoding``
          is not specified.
        """
        with open(self._join(filepath), 'rb') as f:
            data = f.read()
        encoding = encoding or self.encoding
        if encoding is not None:
            return data.decode(encoding)
        return data

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.cleanup()


def tempdir(*args, **kw) -> Callable[[Callable], Callable]:
    """
    A decorator for making a :class:`TempDirectory` available for the
    duration of a test function.

    All arguments and parameters are passed through to the
    :class:`TempDirectory` constructor.
    """
    kw['create'] = False
    l = TempDirectory(*args, **kw)
    return wrap(l.create, l.cleanup)
