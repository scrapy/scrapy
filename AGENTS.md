# Working on Scrapy

Read the
[contributing guide](https://docs.scrapy.org/en/master/contributing.md) first.
This file adds what agents tend to get wrong.

## Before you finish

- Run `pre-commit run --all-files`, `tox -e mypy` and `tox -e pylint`, and
  `tox -e docs` and `tox -e docs-tests` as well if you touched docs or
  docstrings. CI runs these first and skips the test matrix when they fail.
- Run the tests you touched: `tox -e py -- tests/test_foo.py`. Anything after
  `tox -e py --` is passed to pytest.
- If the change depends on what a dependency exposes, run the tests under the
  matching `min-` environment too (see `tox.ini`), e.g.
  `tox -e min-botocore -- tests/test_foo.py`. They pin the oldest supported
  version, which can be years older than the one you have and expose less, so
  assert only on what it has as well.
- Review your own diff. Remove whatever the change does not need: unused
  parameters, dead code, leftover debugging, comments that restate the code.

## Code

- Make the smallest change that solves the issue. Do not add settings,
  parameters or abstractions for needs nobody has yet.
- Prefix new modules, classes, functions, constants and attributes with `_`
  unless users must call them by name. Do not re-export or document private
  APIs.
- Write comments for a reader who has never seen the code any other way.
  Explain what the lines do and why, never what they replaced or which bug
  prompted them. Most lines need no comment.
- Do not write module docstrings. Document classes and functions instead.
- Log messages are f-strings: `logger.debug(f"Ignoring {request.url}")`.
- Use `assert` for invariants and `if` for conditions that can actually
  happen.
- Make new boolean parameters keyword-only.

## Tests

- Cover every line you add, including error branches. Where a branch cannot be
  exercised, mark it `# pragma: no cover`.
- Test through public APIs. If behavior is only reachable through a private
  function, reconsider whether it needs its own test.
- Use `pytest.mark.parametrize` instead of looping over inputs inside one
  test, so that one bad input fails on its own.
- Build components with `build_from_crawler()` from `scrapy.utils.misc` rather
  than calling their constructors.
- Test spiders by crawling them against the mock server, not by calling their
  private methods.
- Use `example.com` or any `.example` domain, never a real one, even in URLs
  that are never fetched.
- New test modules must type-check under `tox -e mypy`.

## Documentation

- API reference lives in docstrings and is pulled in with autodoc. Keep
  docstrings short and link to the narrative docs instead of repeating them.
- Describe parameters in prose, naming them in italics like the standard
  library does (*include_universal*). No `:param:` lists.
- Put `versionadded` and `versionchanged` right after the first paragraph, and
  always write `VERSION` as the version.
- Do not document deprecated features, known bugs, or implementation details
  such as the order in which things happen internally. Never use the
  `deprecated` directive.
- Do not edit `docs/news.rst`. Release notes are written at release time from
  the merged pull requests.
- Say what something is, not what it is not.
- Link instead of duplicating. Put the details in one place; the other pages
  link to it.
- Every example line must show something the other lines do not.
- Mark file names and paths with the `:file:` role.
- Use sentence case for titles. An underline is exactly as long as its title;
  verify with `awk '{print length, $0}'`, not by eye.
- Give new anchors short names without the `topics-` prefix. Keep existing
  anchors.
- Wrap paragraphs at 79 characters.
- `sphinx-scrapy` is pinned in three places that must match: `tox.ini`,
  `docs/requirements.in` (then run `uv pip compile requirements.in -o
  requirements.txt` in `docs/`) and the `rev` in `.pre-commit-config.yaml`.

## Git and GitHub

- One change per pull request. Keep cosmetic changes out of functional
  commits.
- A pull request description is one or two sentences on what and why, plus
  `Closes #N` for every issue or pull request it resolves. The diff and the
  tests already show what changed, so do not summarize them, add section
  headers, or list the files touched.
- Do not open an issue before a pull request. The pull request is enough.
- Comments answer the question asked, in as few words as it takes.
- A commit message is a title. Add a body only when the why does not fit in
  it.
- Once a pull request has been reviewed, only add commits on top. To catch up
  with `master`, merge it in. Never rebase, amend or force-push: pull requests
  are squash-merged, so rewriting history buys nothing and hides what changed
  since the last review.
- When a review asks for changes, update the existing pull request instead of
  opening a new one.
