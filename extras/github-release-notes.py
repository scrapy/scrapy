import re
import sys
from pathlib import Path

DOCS_URL = "https://docs.scrapy.org/en/latest/"


def _absolute_link(match: re.Match[str]) -> str:
    path, _, fragment = match["target"].partition("#")
    path = re.sub(r"\.md$", ".html", path or "news.md")
    return f"]({DOCS_URL}{path}{'#' + fragment if fragment else ''})"


def release_notes(version: str, news_md: str) -> str:
    """Return the GitHub release body of *version*: its highlights, if any,
    and a link to its full release notes.

    *news_md* is the content of :file:`news.md` as built by the Sphinx
    ``markdown`` builder, which resolves cross-references into links.
    """
    section = news_md.split(f"\n## Scrapy {version} (", 1)[1].split("\n## ", 1)[0]
    highlights = ""
    if "\nHighlights:\n" in section:
        block = section.split("\nHighlights:\n", 1)[1].split("\n#", 1)[0]
        highlights = re.sub(r"\n +", " ", block.strip()) + "\n\n"
        highlights = re.sub(
            r"\]\((?P<target>(?!https?://)[^)]*)\)", _absolute_link, highlights
        )
    anchor = "release-" + version.replace(".", "-")
    return f"{highlights}[Full changelog]({DOCS_URL}news.html#{anchor})\n"


if __name__ == "__main__":
    version, path = sys.argv[1:]
    print(release_notes(version, Path(path).read_text(encoding="utf-8")), end="")
