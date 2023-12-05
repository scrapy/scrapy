"""Handles communication on the backend side between frontend and backend

Please keep this file Python 2.7 compatible.
See https://tox.readthedocs.io/en/rewrite/development.html#code-style-guide
"""
from __future__ import print_function

import importlib
import json
import os
import sys
import traceback


class MissingCommand(TypeError):
    """Missing command"""


class BackendProxy:
    def __init__(self, backend_module, backend_obj):
        self.backend_module = backend_module
        self.backend_object = backend_obj
        backend = importlib.import_module(self.backend_module)
        if self.backend_object:
            backend = getattr(backend, self.backend_object)
        self.backend = backend

    def __call__(self, name, *args, **kwargs):
        on_object = self if name.startswith("_") else self.backend
        if not hasattr(on_object, name):
            raise MissingCommand("{!r} has no attribute {!r}".format(on_object, name))
        return getattr(on_object, name)(*args, **kwargs)

    def __str__(self):
        return "{}(backend={})".format(self.__class__.__name__, self.backend)

    def _exit(self):
        return 0

    def _optional_hooks(self):
        return {
            k: hasattr(self.backend, k)
            for k in (
                "get_requires_for_build_sdist",
                "prepare_metadata_for_build_wheel",
                "get_requires_for_build_wheel",
                "build_editable",
                "get_requires_for_build_editable",
                "prepare_metadata_for_build_editable",
            )
        }


def flush():
    sys.stderr.flush()
    sys.stdout.flush()


def run(argv):
    reuse_process = argv[0].lower() == "true"

    try:
        backend_proxy = BackendProxy(argv[1], None if len(argv) == 2 else argv[2])
    except BaseException:
        print("failed to start backend", file=sys.stderr)
        raise
    else:
        print("started backend {}".format(backend_proxy), file=sys.stdout)
    finally:
        flush()  # pragma: no branch
    while True:
        content = read_line()
        if not content:
            continue
        flush()  # flush any output generated before
        try:
            if sys.version_info[0] == 2:  # pragma: no branch # python 2 does not support loading from bytearray
                content = content.decode()  # pragma: no cover
            parsed_message = json.loads(content)
            result_file = parsed_message["result"]
        except Exception:
            # ignore messages that are not valid JSON and contain a valid result path
            print("Backend: incorrect request to backend: {}".format(content), file=sys.stderr)
            flush()
        else:
            result = {}
            try:
                cmd = parsed_message["cmd"]
                print("Backend: run command {} with args {}".format(cmd, parsed_message["kwargs"]))
                outcome = backend_proxy(parsed_message["cmd"], **parsed_message["kwargs"])
                result["return"] = outcome
                if cmd == "_exit":
                    break
            except BaseException as exception:
                result["code"] = exception.code if isinstance(exception, SystemExit) else 1
                result["exc_type"] = exception.__class__.__name__
                result["exc_msg"] = str(exception)
                if not isinstance(exception, MissingCommand):  # for missing command do not print stack
                    traceback.print_exc()
            finally:
                try:
                    with open(result_file, "w") as file_handler:
                        json.dump(result, file_handler)
                except Exception:
                    traceback.print_exc()
                finally:
                    # used as done marker by frontend
                    print("Backend: Wrote response {} to {}".format(result, result_file))
                    flush()  # pragma: no branch
        if reuse_process is False:  # pragma: no branch # no test for reuse process in root test env
            break
    return 0


def read_line(fd=0):
    # for some reason input() seems to break (hangs forever) so instead we read byte by byte the unbuffered stream
    content = bytearray()
    while True:
        char = os.read(fd, 1)
        if not char:
            if not content:
                raise EOFError("EOF without reading anything")  # we didn't get a line at all, let the caller know
            break  # pragma: no cover
        if char == b"\n":
            break
        if char != b"\r":
            content += char
    return content


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
