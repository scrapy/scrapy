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


class TestCmdline:
    def setup_method(self):
        self.env = get_testenv()
        tests_path = Path(__file__).parent.parent
        self.env["PYTHONPATH"] += os.pathsep + str(tests_path.parent)
        self.env["SCRAPY_SETTINGS_MODULE"] = "tests.test_cmdline.settings"

    def _execute(self, *new_args, **kwargs):
        encoding = sys.stdout.encoding or "utf-8"
        args = (sys.executable, "-m", "scrapy.cmdline", *new_args)
        proc = Popen(args, stdout=PIPE, stderr=PIPE, env=self.env, **kwargs)
        stdout, stderr = proc.communicate()
        return stdout.strip().decode(encoding), stderr.strip().decode(encoding)

    def test_default_settings(self):
        stdout, _ = self._execute("settings", "--get", "TEST1")
        assert stdout == "default"

    def test_override_settings_using_set_arg(self):
        stdout, _ = self._execute(
            "settings", "--get", "TEST1", "-s", "TEST1=override"
        )
        assert stdout == "override"

    def test_profiling(self):
        path = Path(tempfile.mkdtemp())
        filename = path / "res.prof"
        try:
            _, log_output = self._execute("version", "--profile", str(filename))
            # Binary dump file must be created
            assert filename.exists()
            # Binary dump must contain valid cProfile data
            out = StringIO()
            stats = pstats.Stats(str(filename), stream=out)
            stats.print_stats()
            out.seek(0)
            stats_text = out.read()
            assert str(Path("scrapy", "commands", "version.py")) in stats_text
            assert "tottime" in stats_text
            # Human-readable summary must appear in the log (stderr)
            assert "cProfile stats" in log_output
            assert "cumtime" in log_output
        finally:
            shutil.rmtree(path)

    def test_override_dict_settings(self):
        EXT_PATH = "tests.test_cmdline.extensions.DummyExtension"
        EXTENSIONS = {EXT_PATH: 200}
        stdout, _ = self._execute(
            "settings",
            "--get",
            "EXTENSIONS",
            "-s",
            "EXTENSIONS=" + json.dumps(EXTENSIONS),
        )
        # XXX: There's gotta be a smarter way to do this...
        assert "..." not in stdout
        for char in ("'", "<", ">"):
            stdout = stdout.replace(char, '"')
        settingsdict = json.loads(stdout)
        assert set(settingsdict.keys()) == set(EXTENSIONS.keys())
        assert settingsdict[EXT_PATH] == 200

    def test_pathlib_path_as_feeds_key(self):
        stdout, _ = self._execute("settings", "--get", "FEEDS")
        assert stdout == json.dumps(
            {"items.csv": {"format": "csv", "fields": ["price", "name"]}}
        )

