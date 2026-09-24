import re
import sys
from pathlib import Path

DOCS_URL = "https://docs.scrapy.org/en/latest/"


def release_notes(version: str, news_md: str) -> str:
    """Return the GitHub release body of *version*: its highlights, or its
    whole release notes if it has no highlights, followed by a link to its
    release notes in the documentation.

    *news_md* is the content of :file:`news.md` as built by the Sphinx
    ``html`` builder, which resolves cross-references into links.
    """
    section = news_md.split(f"\n## Scrapy {version} (", 1)[1].split("\n## ", 1)[0]
    body = section.split("\n", 1)[1]
    if "\nHighlights:\n" in body:
        body = body.split("\nHighlights:\n", 1)[1].split("\n#", 1)[0]
    body = body.strip()
    # GitHub renders every newline of a release body as a line break.
    body = re.sub(r"(?<=\S)\n(?! *([-*] |#|\n)) *", " ", body)
    body = re.sub(r"\]\((?!https?://)([^)\s]*)\.md\b", rf"]({DOCS_URL}\1.html", body)
    body = re.sub(
        r"\[(#\d+)\]\(https://github\.com/scrapy/scrapy/issues/\d+\)", r"\1", body
    )
    anchor = "release-" + version.replace(".", "-")
    return f"{body}\n\n[Full changelog]({DOCS_URL}news.html#{anchor})\n"


if __name__ == "__main__":
    version, path = sys.argv[1:]
    print(release_notes(version, Path(path).read_text(encoding="utf-8")), end="")
