# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/nedbat/coveragepy/blob/master/NOTICE.txt

"""SQLite abstraction for coverage.py"""

from __future__ import annotations

import contextlib
import re
import sqlite3

from typing import cast, Any, Iterable, Iterator, List, Optional, Tuple

from coverage.debug import auto_repr, clipped_repr, exc_one_line
from coverage.exceptions import DataError
from coverage.types import TDebugCtl


class SqliteDb:
    """A simple abstraction over a SQLite database.

    Use as a context manager, then you can use it like a
    :class:`python:sqlite3.Connection` object::

        with SqliteDb(filename, debug_control) as db:
            with db.execute("select a, b from some_table") as cur:
                for a, b in cur:
                    etc(a, b)

    """
    def __init__(self, filename: str, debug: TDebugCtl) -> None:
        self.debug = debug
        self.filename = filename
        self.nest = 0
        self.con: Optional[sqlite3.Connection] = None

    __repr__ = auto_repr

    def _connect(self) -> None:
        """Connect to the db and do universal initialization."""
        if self.con is not None:
            return

        # It can happen that Python switches threads while the tracer writes
        # data. The second thread will also try to write to the data,
        # effectively causing a nested context. However, given the idempotent
        # nature of the tracer operations, sharing a connection among threads
        # is not a problem.
        if self.debug.should("sql"):
            self.debug.write(f"Connecting to {self.filename!r}")
        try:
            self.con = sqlite3.connect(self.filename, check_same_thread=False)
        except sqlite3.Error as exc:
            raise DataError(f"Couldn't use data file {self.filename!r}: {exc}") from exc

        self.con.create_function("REGEXP", 2, lambda txt, pat: re.search(txt, pat) is not None)

        # Turning off journal_mode can speed up writing. It can't always be
        # disabled, so we have to be prepared for *-journal files elsewhere.
        # In Python 3.12+, we can change the config to allow journal_mode=off.
        if hasattr(sqlite3, "SQLITE_DBCONFIG_DEFENSIVE"):
            # Turn off defensive mode, so that journal_mode=off can succeed.
            self.con.setconfig(     # type: ignore[attr-defined]
                sqlite3.SQLITE_DBCONFIG_DEFENSIVE, False
            )

        # This pragma makes writing faster. It disables rollbacks, but we never need them.
        self.execute_void("pragma journal_mode=off")

        # This pragma makes writing faster. It can fail in unusual situations
        # (https://github.com/nedbat/coveragepy/issues/1646), so use fail_ok=True
        # to keep things going.
        self.execute_void("pragma synchronous=off", fail_ok=True)

    def close(self) -> None:
        """If needed, close the connection."""
        if self.con is not None and self.filename != ":memory:":
            self.con.close()
            self.con = None

    def __enter__(self) -> SqliteDb:
        if self.nest == 0:
            self._connect()
            assert self.con is not None
            self.con.__enter__()
        self.nest += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:     # type: ignore[no-untyped-def]
        self.nest -= 1
        if self.nest == 0:
            try:
                assert self.con is not None
                self.con.__exit__(exc_type, exc_value, traceback)
                self.close()
            except Exception as exc:
                if self.debug.should("sql"):
                    self.debug.write(f"EXCEPTION from __exit__: {exc_one_line(exc)}")
                raise DataError(f"Couldn't end data file {self.filename!r}: {exc}") from exc

    def _execute(self, sql: str, parameters: Iterable[Any]) -> sqlite3.Cursor:
        """Same as :meth:`python:sqlite3.Connection.execute`."""
        if self.debug.should("sql"):
            tail = f" with {parameters!r}" if parameters else ""
            self.debug.write(f"Executing {sql!r}{tail}")
        try:
            assert self.con is not None
            try:
                return self.con.execute(sql, parameters)    # type: ignore[arg-type]
            except Exception:
                # In some cases, an error might happen that isn't really an
                # error.  Try again immediately.
                # https://github.com/nedbat/coveragepy/issues/1010
                return self.con.execute(sql, parameters)    # type: ignore[arg-type]
        except sqlite3.Error as exc:
            msg = str(exc)
            if self.filename != ":memory:":
                try:
                    # `execute` is the first thing we do with the database, so try
                    # hard to provide useful hints if something goes wrong now.
                    with open(self.filename, "rb") as bad_file:
                        cov4_sig = b"!coverage.py: This is a private format"
                        if bad_file.read(len(cov4_sig)) == cov4_sig:
                            msg = (
                                "Looks like a coverage 4.x data file. " +
                                "Are you mixing versions of coverage?"
                            )
                except Exception:
                    pass
            if self.debug.should("sql"):
                self.debug.write(f"EXCEPTION from execute: {exc_one_line(exc)}")
            raise DataError(f"Couldn't use data file {self.filename!r}: {msg}") from exc

    @contextlib.contextmanager
    def execute(
        self,
        sql: str,
        parameters: Iterable[Any] = (),
    ) -> Iterator[sqlite3.Cursor]:
        """Context managed :meth:`python:sqlite3.Connection.execute`.

        Use with a ``with`` statement to auto-close the returned cursor.
        """
        cur = self._execute(sql, parameters)
        try:
            yield cur
        finally:
            cur.close()

    def execute_void(self, sql: str, parameters: Iterable[Any] = (), fail_ok: bool = False) -> None:
        """Same as :meth:`python:sqlite3.Connection.execute` when you don't need the cursor.

        If `fail_ok` is True, then SQLite errors are ignored.
        """
        try:
            # PyPy needs the .close() calls here, or sqlite gets twisted up:
            # https://bitbucket.org/pypy/pypy/issues/2872/default-isolation-mode-is-different-on
            self._execute(sql, parameters).close()
        except DataError:
            if not fail_ok:
                raise

    def execute_for_rowid(self, sql: str, parameters: Iterable[Any] = ()) -> int:
        """Like execute, but returns the lastrowid."""
        with self.execute(sql, parameters) as cur:
            assert cur.lastrowid is not None
            rowid: int = cur.lastrowid
        if self.debug.should("sqldata"):
            self.debug.write(f"Row id result: {rowid!r}")
        return rowid

    def execute_one(self, sql: str, parameters: Iterable[Any] = ()) -> Optional[Tuple[Any, ...]]:
        """Execute a statement and return the one row that results.

        This is like execute(sql, parameters).fetchone(), except it is
        correct in reading the entire result set.  This will raise an
        exception if more than one row results.

        Returns a row, or None if there were no rows.
        """
        with self.execute(sql, parameters) as cur:
            rows = list(cur)
        if len(rows) == 0:
            return None
        elif len(rows) == 1:
            return cast(Tuple[Any, ...], rows[0])
        else:
            raise AssertionError(f"SQL {sql!r} shouldn't return {len(rows)} rows")

    def _executemany(self, sql: str, data: List[Any]) -> sqlite3.Cursor:
        """Same as :meth:`python:sqlite3.Connection.executemany`."""
        if self.debug.should("sql"):
            final = ":" if self.debug.should("sqldata") else ""
            self.debug.write(f"Executing many {sql!r} with {len(data)} rows{final}")
            if self.debug.should("sqldata"):
                for i, row in enumerate(data):
                    self.debug.write(f"{i:4d}: {row!r}")
        assert self.con is not None
        try:
            return self.con.executemany(sql, data)
        except Exception:
            # In some cases, an error might happen that isn't really an
            # error.  Try again immediately.
            # https://github.com/nedbat/coveragepy/issues/1010
            return self.con.executemany(sql, data)

    def executemany_void(self, sql: str, data: Iterable[Any]) -> None:
        """Same as :meth:`python:sqlite3.Connection.executemany` when you don't need the cursor."""
        data = list(data)
        if data:
            self._executemany(sql, data).close()

    def executescript(self, script: str) -> None:
        """Same as :meth:`python:sqlite3.Connection.executescript`."""
        if self.debug.should("sql"):
            self.debug.write("Executing script with {} chars: {}".format(
                len(script), clipped_repr(script, 100),
            ))
        assert self.con is not None
        self.con.executescript(script).close()

    def dump(self) -> str:
        """Return a multi-line string, the SQL dump of the database."""
        assert self.con is not None
        return "\n".join(self.con.iterdump())
