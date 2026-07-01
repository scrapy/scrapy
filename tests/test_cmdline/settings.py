from pathlib import Path

EXTENSIONS = {
    "tests.test_cmdline.extensions.DummyExtension": 0,
}

TEST1 = "default"

FEEDS = {
    Path("items.csv"): {
        "format": "csv",
        "fields": ["price", "name"],
    },
}
