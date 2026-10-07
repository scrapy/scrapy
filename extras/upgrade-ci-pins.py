import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# tox environments whose pins are CI tool versions, as opposed to the minimum
# supported versions of dependencies.
TOX_ENVS = ("mypy", "mypy-tests", "pylint", "twinecheck")

# GitHub Actions releases younger than this are skipped, to give the ecosystem
# time to spot compromised or broken releases before they reach CI. Keep in
# sync with the cooldown in .github/dependabot.yml.
COOLDOWN = timedelta(days=7)


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", re.sub(r"\[.*", "", name)).lower()


def _section(tox_ini: str, name: str) -> re.Match[str]:
    match = re.search(
        rf"^\[{re.escape(name)}\]\n(.*?)(?=^\[|\Z)", tox_ini, re.MULTILINE | re.DOTALL
    )
    assert match, name
    return match


def _deps(tox_ini: str, name: str) -> list[str]:
    block = re.search(
        r"^deps =\n((?:[ \t]+.*\n)*)", _section(tox_ini, name)[1], re.MULTILINE
    )
    if not block:
        return []
    deps = (re.sub(r"\s*#.*", "", line).strip() for line in block[1].splitlines())
    return [dep for dep in deps if dep]


def _requirements(tox_ini: str, name: str) -> list[str]:
    requirements = []
    for dep in _deps(tox_ini, name):
        if match := re.fullmatch(r"\{\[(.+)\]deps\}", dep):
            requirements += _requirements(tox_ini, match[1])
        else:
            requirements.append(dep)
    return requirements


def _resolve(requirements: list[str], python: str) -> dict[str, str]:
    output = subprocess.run(  # noqa: S603
        [
            *("uv", "pip", "compile", "--python-version", python),
            *("--no-header", "--no-annotate", "--quiet", "-"),
        ],
        input="\n".join(requirements),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {
        _normalize(match[1]): match[2]
        for match in re.finditer(r"^(\S+)==(\S+)", output, re.MULTILINE)
    }


def _upgrade_tox_env(tox_ini: str, env: str) -> str:
    """Return *tox_ini* with the pins of *env* upgraded to the latest versions
    that can be installed together with Scrapy and the rest of the
    requirements of *env*, for its Python version.

    Pins that *env* gets from other sections are kept.
    """
    name = f"testenv:{env}"
    section = _section(tox_ini, name)
    body = section[1]
    python = re.search(r"^basepython = python(\S*)", body, re.MULTILINE)
    assert python
    version = python[1]
    if version == "3":
        version = f"{sys.version_info.major}.{sys.version_info.minor}"
    own = {dep: re.sub(r"==[^;\s]+", "", dep) for dep in _deps(tox_ini, name)}
    requirements = [own.get(dep, dep) for dep in _requirements(tox_ini, name)]
    versions = _resolve([*requirements, "."], version)
    body = re.sub(
        r"^([ \t]+)([\w.\-\[\],]+)==([^;\s]+)",
        lambda m: f"{m[1]}{m[2]}=={versions.get(_normalize(m[2]), m[3])}",
        body,
        flags=re.MULTILINE,
    )
    return tox_ini[: section.start(1)] + body + tox_ini[section.end(1) :]


def _github(path: str) -> Any:
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"https://api.github.com/{path}", headers=headers)
    with urlopen(request) as response:  # noqa: S310
        return json.load(response)


def _upgrade_actions(cutoff: datetime) -> None:
    """Pin every GitHub action used in workflows to the commit of its latest
    release published before *cutoff*.
    """
    workflows = list(Path(".github/workflows").glob("*.yml"))
    pattern = r"(uses: ([\w.-]+/[\w.-]+)[\w./-]*@)[0-9a-f]{40} # \S+"
    repos = {
        match[2]
        for path in workflows
        for match in re.finditer(pattern, path.read_text(encoding="utf-8"))
    }
    pins = {}
    for repo in sorted(repos):
        try:
            release = _github(f"repos/{repo}/releases/latest")
        except HTTPError as error:
            if error.code != 404:
                raise
            print(f"{repo} has no releases, keeping its pin")
            continue
        if datetime.fromisoformat(release["published_at"]) > cutoff:
            print(f"{repo} {release['tag_name']} is too recent, keeping its pin")
            continue
        sha = _github(f"repos/{repo}/commits/{release['tag_name']}")["sha"]
        pins[repo] = f"{sha} # {release['tag_name']}"
    for path in workflows:
        text = re.sub(
            pattern,
            lambda m: f"{m[1]}{pins[m[2]]}" if m[2] in pins else m[0],
            path.read_text(encoding="utf-8"),
        )
        path.write_text(text, encoding="utf-8")


def main() -> None:
    python = f"{sys.version_info.major}.{sys.version_info.minor}"

    _upgrade_actions(datetime.now(UTC) - COOLDOWN)

    subprocess.run(["pre-commit", "autoupdate"], check=True)  # noqa: S607

    # pre-commit autoupdate does not upgrade additional_dependencies.
    pre_commit = Path(".pre-commit-config.yaml")
    config = re.sub(
        r"^(\s+- )([\w.\-]+)==(\S+)$",
        lambda m: f"{m[1]}{m[2]}=={_resolve([m[2]], python)[_normalize(m[2])]}",
        pre_commit.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    pre_commit.write_text(config, encoding="utf-8")

    # sphinx-scrapy syncs its pins in tox.ini and docs/requirements.in with its
    # pre-commit rev, and sets the Python version of .readthedocs.yml to the
    # latest one that Read the Docs supports.
    subprocess.run(
        ["pre-commit", "run", "sphinx-scrapy", "--all-files"],  # noqa: S607
        check=False,
    )
    docs_python = re.search(
        r'^    python: "([^"]+)"',
        Path(".readthedocs.yml").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert docs_python
    ci = Path(".github/workflows/ci.yml")
    text = re.sub(
        r'(# Keep in sync with \.readthedocs\.yml\.\n\s+- python-version: ")[^"]+',
        rf"\g<1>{docs_python[1]}",
        ci.read_text(encoding="utf-8"),
    )
    ci.write_text(text, encoding="utf-8")
    subprocess.run(  # noqa: S603
        [
            *("uv", "pip", "compile", "--upgrade", "--quiet", "requirements.in"),
            *("-o", "requirements.txt", "--python-version", docs_python[1]),
        ],
        cwd="docs",
        check=True,
    )

    tox_ini = Path("tox.ini").read_text(encoding="utf-8")
    for env in TOX_ENVS:
        tox_ini = _upgrade_tox_env(tox_ini, env)
    Path("tox.ini").write_text(tox_ini, encoding="utf-8")


if __name__ == "__main__":
    main()
