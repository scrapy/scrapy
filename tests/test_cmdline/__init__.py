import ast
import json
import os
import pstats
import shutil
import sys
import tempfile
from io import StringIO
from pathlib import Path
from subprocess import PIPE, Popen

from scrapy.utils.test import get_testenv


def _execute(*new_args, **kwargs):
    env = get_testenv()
    tests_path = Path(__file__).parent.parent
    env["PYTHONPATH"] += os.pathsep + str(tests_path.parent)
    env["SCRAPY_SETTINGS_MODULE"] = "tests.test_cmdline.settings"
    encoding = sys.stdout.encoding or "utf-8"
    args = (sys.executable, "-m", "scrapy.cmdline", *new_args)
    proc = Popen(args, stdout=PIPE, stderr=PIPE, env=env, **kwargs)
    comm = proc.communicate()[0].strip()
    return comm.decode(encoding)


def test_default_settings():
    assert _execute("settings", "--get", "TEST1") == "default"


def test_override_settings_using_set_arg():
    assert _execute("settings", "--get", "TEST1", "-s", "TEST1=override") == "override"


def test_profiling():
    path = Path(tempfile.mkdtemp())
    filename = path / "res.prof"
    try:
        _execute("version", "--profile", str(filename))
        assert filename.exists()
        out = StringIO()
        stats = pstats.Stats(str(filename), stream=out)
        stats.print_stats()
        out.seek(0)
        stats = out.read()
        assert str(Path("scrapy", "commands", "version.py")) in stats
        assert "tottime" in stats
    finally:
        shutil.rmtree(path)


def test_override_dict_settings():
    EXT_PATH = "tests.test_cmdline.extensions.DummyExtension"
    EXTENSIONS = {EXT_PATH: 200}
    settingsstr = _execute(
        "settings",
        "--get",
        "EXTENSIONS",
        "-s",
        "EXTENSIONS=" + json.dumps(EXTENSIONS),
    )
    assert "..." not in settingsstr
    settingsdict = ast.literal_eval(settingsstr)
    assert set(settingsdict.keys()) == set(EXTENSIONS.keys())
    assert settingsdict[EXT_PATH] == 200


def test_pathlib_path_as_feeds_key():
    assert _execute("settings", "--get", "FEEDS") == json.dumps(
        {"items.csv": {"format": "csv", "fields": ["price", "name"]}}
    )
