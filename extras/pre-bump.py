import re
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

TITLE = re.compile(
    r"^Scrapy (\d+\.\d+\.\d+) \((unreleased|\d{4}-\d{2}-\d{2})\)$", re.MULTILINE
)


def _git_grep(pattern: str) -> list[str]:
    return subprocess.run(  # noqa: S603
        ["git", "grep", "-nE", pattern, "--", "docs", "scrapy"],  # noqa: S607
        capture_output=True,
        check=False,
        text=True,
    ).stdout.splitlines()


def placeholders() -> list[str]:
    """Return the ``VERSION`` and ``PREVIOUS_VERSION`` placeholders, which
    must be replaced with actual versions before a release.
    """
    return _git_grep(r"(^|[^/\"_A-Z`])(PREVIOUS_)?VERSION\b")


def old_directives(today: date) -> list[str]:
    """Return the ``versionadded`` and ``versionchanged`` directives that a
    major or minor release made on *today* must remove, i.e. those of
    releases more than 3 years old.
    """
    news = Path("docs/news.rst").read_text(encoding="utf-8")
    new_version = next((m[1] for m in TITLE.finditer(news) if m[2] == "unreleased"), "")
    if not new_version.endswith(".0"):
        return []
    for path in Path("docs/news").glob("*.rst"):
        news += path.read_text(encoding="utf-8")
    released = {
        m[1]: date.fromisoformat(m[2])
        for m in TITLE.finditer(news)
        if m[2] != "unreleased"
    }
    # February 29 becomes February 28.
    cutoff = date(
        today.year - 3, today.month, min(today.day, 28 if today.month == 2 else 31)
    )
    return [
        line
        for line in _git_grep(r"\.\. version(added|changed):: *[0-9]")
        if (m := re.search(r":: *(\d+\.\d+)(\.\d+)?", line))
        and released.get(f"{m[1]}{m[2] or '.0'}", today) < cutoff
    ]


if __name__ == "__main__":
    failed = False
    for message, lines in (
        ("Replace these placeholders:", placeholders()),
        (
            "Remove these directives, older than 3 years:",
            old_directives(datetime.now(UTC).date()),
        ),
    ):
        if lines:
            print(message, *lines, sep="\n")
            failed = True
    sys.exit(failed)
