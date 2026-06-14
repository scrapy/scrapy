# .github — Repository Automation & Contributing Guide

This directory contains all GitHub-specific configuration: CI/CD workflows, issue templates, pull request templates, and tooling documentation.

---

## 📁 Directory Structure

```
.github/
├── workflows/                  # GitHub Actions CI/CD pipelines
│   ├── tests-ubuntu.yml        # Test matrix on Ubuntu (Python 3.10–3.14, PyPy)
│   ├── tests-macos.yml         # Test matrix on macOS
│   ├── tests-windows.yml       # Test matrix on Windows
│   ├── checks.yml              # Static analysis: pylint, mypy, docs, twine
│   ├── publish.yml             # PyPI publish on release
│   └── auto-close-llm-pr.yml   # Auto-close unreviewed LLM-generated PRs
├── ISSUE_TEMPLATE/
│   ├── bug_report.md           # Bug report template
│   ├── feature_request.md      # Feature request template
│   └── question.md             # General question template
├── pull_request_template.md    # PR checklist and contributor guidance
└── README.md                   # This file
```

---

## ⚙️ CI/CD Workflows

### Test Workflows

Tests run automatically on every push to `master` / version branches, and on every pull request.

| Workflow | OS | Python versions |
| --- | --- | --- |
| `tests-ubuntu.yml` | Ubuntu | 3.10, 3.11, 3.12, 3.13, 3.14, PyPy 3.11 |
| `tests-macos.yml` | macOS | 3.14 |
| `tests-windows.yml` | Windows | 3.14 |

Each matrix entry runs `tox` with a specific `TOXENV`, covering:

- **Standard test environments** (`py`, `default-reactor`, `no-reactor`)
- **Minimum dependency environments** (`min`, `min-extra-deps`, `min-botocore`, etc.)
- **Extra dependency environments** (`extra-deps`, `botocore`, `mitmproxy`)
- **PyPy environments** (`pypy3`, `pypy3-extra-deps`)

Coverage reports are uploaded to [Codecov](https://codecov.io/) at the end of each test run.

### Checks Workflow (`checks.yml`)

Runs on every push and PR:

| Check | Tool | Python |
| --- | --- | --- |
| Type checking | `mypy` | 3.10 |
| Type checking (tests) | `mypy-tests` | 3.10 |
| Linting | `pylint` | 3.14 |
| Documentation build | `docs` | 3.14 |
| Documentation tests | `docs-tests` | 3.13 |
| Package check | `twinecheck` | 3.14 |
| Pre-commit hooks | `pre-commit` | any |

### Publish Workflow (`publish.yml`)

Publishes to [PyPI](https://pypi.org/project/Scrapy/) when a new GitHub Release is created.

---

## 🧠 Delta Smart Test Selection (Local Development)

[**Delta**](https://deltatest.dev) (`deltatest-cli`) is installed in the local `.venv` and enables **running only the tests affected by your code changes** — dramatically reducing feedback time during development.

### How it works

1. Delta tracks which tests execute which lines of source code via `coverage.py` context tracking.
2. On each run, it diffs your working branch against a base branch (e.g. `master`).
3. Only the tests that cover the changed lines are selected and executed.

### Usage

```bash
# Run only tests affected by your changes vs master
.venv/bin/delta run --local --base-branch master

# Preview which tests would run (dry run)
.venv/bin/delta run --local --base-branch master --dry-run

# Explain exactly why each test was selected
.venv/bin/delta run --local --base-branch master --explain

# Rebuild the coverage mapping database (first time or after large refactors)
.venv/bin/delta build-mapping --local
```

### Benchmark Results

A helper script at [`extras/delta_benchmark.py`](../extras/delta_benchmark.py) measures the actual savings Delta provides per commit. Example result on this project:

| Commit | No Delta (P/F/S/Total) | Delta (P/F/S/Total) | Test Savings | Time Savings |
| --- | --- | --- | --- | --- |
| Add coverage for `Item.__delitem__()` | 3645 / 0 / 478 / 4123 | 125 / 0 / 0 / 125 | **97.0%** | **87.2%** (395s → 51s) |

Run the benchmark yourself:
```bash
.venv/bin/python extras/delta_benchmark.py
```

---

## 💡 Idea: Delta as a GitHub App / Check

> **Can Delta pre-check every commit and run only relevant tests before any full CI job starts?**

Yes — and here's how it could work:

### Architecture Overview

```
PR opened / commit pushed
         │
         ▼
┌─────────────────────────┐
│  GitHub App Webhook     │  ← registers a "pending" check on the commit
│  (Node.js / Python)     │
└────────────┬────────────┘
             │  git diff (changed files + lines)
             ▼
┌─────────────────────────┐
│  Delta Cloud API        │  ← queries which tests cover changed lines
│  (test_mapping.db)      │
└────────────┬────────────┘
             │  list of affected test IDs
             ▼
┌─────────────────────────┐
│  Ephemeral Runner       │  ← runs ONLY the selected tests (fast feedback)
│  (GitHub Actions / pod) │
└────────────┬────────────┘
             │  pass / fail
             ▼
┌─────────────────────────┐
│  GitHub Check API       │  ← posts result as a required status check
│  "Delta Pre-Check ✅"   │
└─────────────────────────┘
             │
             ▼  (if passed, full CI matrix starts in parallel or is skipped)
    Full CI (tox matrix)
```

### Implementation Steps

1. **Register a GitHub App** with `checks:write`, `pull_requests:read`, and `contents:read` permissions.
2. **Webhook endpoint** listens for `pull_request` and `push` events.
3. **On event**: create a `check_run` in `in_progress` state via the [Checks API](https://docs.github.com/en/rest/checks).
4. **Query Delta Cloud** (or local DB) with the changed files/lines to get affected test IDs.
5. **Spin up a runner** (GitHub Actions `workflow_dispatch`, a container, or a self-hosted runner) and run only those tests.
6. **Report result** back to the commit via `PATCH /check_runs/{check_run_id}` with `conclusion: success | failure`.
7. **Gate the full CI matrix** behind this check using [branch protection rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) — the full matrix only starts if the Delta pre-check passes, or runs in parallel and can be cancelled early on failure.

### Key Benefits

- 🚀 **Instant feedback** (seconds instead of minutes) on whether the changed code breaks any related tests.
- 💰 **CI cost reduction** — full matrix only runs when the fast pre-check passes.
- 🔁 **Incremental**: the mapping database grows more accurate with every run.

### Existing Integration Point

The `delta.pytest_plugin` is already installed in this project. Passing `--delta` to pytest activates smart test filtering inline, which is exactly what the runner step above would use:

```bash
pytest --delta --delta-local --delta-base origin/master
```

---

## 🤝 Contributing

Please read the [contributing guide](../CONTRIBUTING.md) and the [pull request template](pull_request_template.md) before submitting changes.

Key points:
- Run `tox` locally and ensure all existing tests pass.
- Add or update relevant tests — all new code should have complete test coverage.
- Update documentation for any user-facing changes.
- Reference any issues you are resolving (e.g. `Resolves #123`).
