#!/usr/bin/env python3
import os
import sys
import subprocess
import re
import json
import xml.etree.ElementTree as ET
from pathlib import Path

def run_cmd(cmd, cwd=None, capture=True):
    """Run a shell command and return status, stdout, stderr."""
    print(f"Running: {' '.join(cmd)}")
    if capture:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
    else:
        result = subprocess.run(cmd, cwd=cwd)
        return result.returncode, "", ""

def get_git_root():
    _, stdout, _ = run_cmd(["git", "rev-parse", "--show-toplevel"])
    return Path(stdout.strip())

def is_git_clean():
    # Check for unstaged changes to tracked files
    ret1, _, _ = run_cmd(["git", "diff", "--quiet"])
    # Check for staged changes to tracked files
    ret2, _, _ = run_cmd(["git", "diff", "--cached", "--quiet"])
    return ret1 == 0 and ret2 == 0

def parse_junit_xml(xml_path):
    """Parse junit XML report to get test count and total duration."""
    if not os.path.exists(xml_path):
        return {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "time": 0.0}
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # In JUnit XML, the root is usually <testsuites> or <testsuite>
        tests = int(root.attrib.get("tests", 0))
        failures = int(root.attrib.get("failures", 0))
        errors = int(root.attrib.get("errors", 0))
        skipped = int(root.attrib.get("skipped", 0))
        time = float(root.attrib.get("time", 0.0))
        
        # If <testsuites> has child <testsuite>s, we might need to sum them if root is empty
        if tests == 0 and len(root) > 0:
            for suite in root.findall("testsuite"):
                tests += int(suite.attrib.get("tests", 0))
                failures += int(suite.attrib.get("failures", 0))
                errors += int(suite.attrib.get("errors", 0))
                skipped += int(suite.attrib.get("skipped", 0))
                time += float(suite.attrib.get("time", 0.0))
                
        passed = tests - failures - errors - skipped
        return {
            "tests": tests,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
            "passed": passed,
            "time": time
        }
    except Exception as e:
        print(f"Error parsing XML {xml_path}: {e}")
        return {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "time": 0.0}

def main():
    repo_root = get_git_root()
    os.chdir(repo_root)

    print("=== Delta Savings Benchmarking Script ===")

    if not is_git_clean():
        print("Error: Git working directory is not clean. Please stash or commit your changes first.")
        sys.exit(1)

    # Get current branch and HEAD commit so we can restore it later
    _, active_branch, _ = run_cmd(["git", "branch", "--show-current"])
    active_branch = active_branch.strip()
    _, orig_head, _ = run_cmd(["git", "rev-parse", "HEAD"])
    orig_head = orig_head.strip()

    print(f"Current branch: {active_branch}")
    print(f"Original HEAD: {orig_head}")

    # 1. Get merges/commits from the last day.
    # We look for commits matching the pattern "Merge pull request" or merges in general.
    # Fallback to last 5 commits if none found in the last day.
    cmd = ["git", "log", "--merges", "--since=1 day ago", "--reverse", "--oneline"]
    status, stdout, _ = run_cmd(cmd)
    
    commits = []
    if status == 0 and stdout.strip():
        for line in stdout.strip().split("\n"):
            parts = line.split(" ", 1)
            commits.append((parts[0], parts[1]))
        print(f"Found {len(commits)} merge commits in the last day.")
    else:
        print("No merge commits found in the last day. Checking for regular commits in the last day...")
        cmd = ["git", "log", "--since=1 day ago", "--reverse", "--oneline"]
        status, stdout, _ = run_cmd(cmd)
        if status == 0 and stdout.strip():
            for line in stdout.strip().split("\n"):
                parts = line.split(" ", 1)
                commits.append((parts[0], parts[1]))
            print(f"Found {len(commits)} commits in the last day.")
        else:
            print("No commits found in the last day. Falling back to the last 10 commits on the current branch.")
            cmd = ["git", "log", "-n", "10", "--reverse", "--oneline"]
            status, stdout, _ = run_cmd(cmd)
            for line in stdout.strip().split("\n"):
                parts = line.split(" ", 1)
                commits.append((parts[0], parts[1]))

    if not commits:
        print("No commits found to benchmark. Exiting.")
        sys.exit(1)

    # Benchmark up to 10 commits
    commits = commits[:10]

    print("\nCommits to evaluate:")
    for sha, desc in commits:
        print(f"  - {sha}: {desc}")

    results = []

    # Path to local virtual environment pytest and delta
    venv_python = repo_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = Path(sys.executable) # Fallback to current python
    
    # We will use temporary xml files for the results
    xml_with = repo_root / ".delta_bench_with.xml"
    xml_without = repo_root / ".delta_bench_without.xml"

    try:
        for idx, (sha, desc) in enumerate(commits):
            print(f"\n==================================================")
            print(f"Evaluating commit {idx+1}/{len(commits)}: {sha} ({desc})")
            print(f"==================================================")

            # Get parent commit hash
            _, parent_stdout, _ = run_cmd(["git", "rev-parse", f"{sha}^1"])
            parent_sha = parent_stdout.strip()

            # Checkout the commit
            print(f"Checking out {sha}...")
            run_cmd(["git", "checkout", sha])

            # Cleanup old XML files
            for p in [xml_with, xml_without]:
                if p.exists():
                    p.unlink()

            # --- 1. Run WITHOUT Delta (Full pytest run) ---
            print("\n>>> Running WITHOUT Delta (Full test suite)...")
            # We run pytest directly using python from the venv
            # We pass --junitxml to store the results
            run_cmd([
                str(venv_python), "-m", "pytest",
                "--cov-config=pyproject.toml",
                "--cov=scrapy",
                "--cov-report=",
                "--cov-report=term-missing",
                "--cov-report=xml",
                f"--junitxml={xml_without}",
                "-o", "junit_family=legacy",
                "--durations=10",
                "scrapy", "tests",
                "--doctest-modules"
            ], capture=False)
            stats_without = parse_junit_xml(str(xml_without))

            # --- 2. Run WITH Delta ---
            print("\n>>> Running WITH Delta...")
            # We run delta run pointing to the parent commit as base branch
            run_cmd([
                str(repo_root / ".venv" / "bin" / "delta"), "run",
                "--base-branch", parent_sha,
                "--",
                f"--junitxml={xml_with}"
            ], capture=False)
            stats_with = parse_junit_xml(str(xml_with))

            # Calculate savings
            tests_saved = stats_without["tests"] - stats_with["tests"]
            tests_saved_pct = (tests_saved / stats_without["tests"] * 100) if stats_without["tests"] > 0 else 0.0
            
            time_saved = stats_without["time"] - stats_with["time"]
            time_saved_pct = (time_saved / stats_without["time"] * 100) if stats_without["time"] > 0 else 0.0

            results.append({
                "sha": sha,
                "desc": desc,
                "without": stats_without,
                "with": stats_with,
                "savings": {
                    "tests_count": tests_saved,
                    "tests_pct": tests_saved_pct,
                    "time_seconds": time_saved,
                    "time_pct": time_saved_pct
                }
            })

            print(f"\nCommit {sha} Summary:")
            print(f"  Without Delta: {stats_without['tests']} tests (Passed: {stats_without['passed']}, Failed: {stats_without['failures'] + stats_without['errors']}, Skipped: {stats_without['skipped']}) in {stats_without['time']:.2f}s")
            print(f"  With Delta:    {stats_with['tests']} tests (Passed: {stats_with['passed']}, Failed: {stats_with['failures'] + stats_with['errors']}, Skipped: {stats_with['skipped']}) in {stats_with['time']:.2f}s")
            print(f"  Savings:       {tests_saved} tests ({tests_saved_pct:.1f}%), {time_saved:.2f}s ({time_saved_pct:.1f}%)")

    finally:
        # Restore original HEAD state
        print("\nRestoring original branch and HEAD...")
        run_cmd(["git", "checkout", active_branch if active_branch else orig_head])
        
        # Cleanup temporary files
        for p in [xml_with, xml_without]:
            if p.exists():
                p.unlink()

    # Generate Markdown Report Table
    print("\n\n" + "="*80)
    print("BENCHMARK RESULTS")
    print("="*80)
    
    report_lines = []
    report_lines.append("# Delta Savings Benchmark Report\n")
    report_lines.append("| Commit | Description | No Delta (P/F/S/Total) | Delta (P/F/S/Total) | Test Savings | Time (No Delta) | Time (Delta) | Time Savings |")
    report_lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    
    total_tests_without = 0
    total_tests_with = 0
    total_time_without = 0.0
    total_time_with = 0.0
    total_passed_without = 0
    total_failed_without = 0
    total_skipped_without = 0
    total_passed_with = 0
    total_failed_with = 0
    total_skipped_with = 0

    for res in results:
        sha_short = res["sha"][:7]
        desc_short = res["desc"][:40] + "..." if len(res["desc"]) > 40 else res["desc"]
        
        without_t = res["without"]["tests"]
        without_p = res["without"]["passed"]
        without_f = res["without"]["failures"] + res["without"]["errors"]
        without_s = res["without"]["skipped"]
        
        with_t = res["with"]["tests"]
        with_p = res["with"]["passed"]
        with_f = res["with"]["failures"] + res["with"]["errors"]
        with_s = res["with"]["skipped"]
        
        without_time = res["without"]["time"]
        with_time = res["with"]["time"]
        
        total_tests_without += without_t
        total_tests_with += with_t
        total_time_without += without_time
        total_time_with += with_time
        
        total_passed_without += without_p
        total_failed_without += without_f
        total_skipped_without += without_s
        total_passed_with += with_p
        total_failed_with += with_f
        total_skipped_with += with_s
        
        test_sav_str = f"{res['savings']['tests_count']} ({res['savings']['tests_pct']:.1f}%)"
        time_sav_str = f"{res['savings']['time_seconds']:.2f}s ({res['savings']['time_pct']:.1f}%)"
        
        no_delta_str = f"{without_p} / {without_f} / {without_s} / **{without_t}**"
        delta_str = f"{with_p} / {with_f} / {with_s} / **{with_t}**"
        
        report_lines.append(f"| {sha_short} | {desc_short} | {no_delta_str} | {delta_str} | {test_sav_str} | {without_time:.2f}s | {with_time:.2f}s | {time_sav_str} |")

    # Add totals row
    total_tests_saved = total_tests_without - total_tests_with
    total_tests_saved_pct = (total_tests_saved / total_tests_without * 100) if total_tests_without > 0 else 0.0
    total_time_saved = total_time_without - total_time_with
    total_time_saved_pct = (total_time_saved / total_time_without * 100) if total_time_without > 0 else 0.0

    total_test_sav_str = f"**{total_tests_saved} ({total_tests_saved_pct:.1f}%)**"
    total_time_sav_str = f"**{total_time_saved:.2f}s ({total_time_saved_pct:.1f}%)**"
    
    total_no_delta_str = f"**{total_passed_without} / {total_failed_without} / {total_skipped_without} / {total_tests_without}**"
    total_delta_str = f"**{total_passed_with} / {total_failed_with} / {total_skipped_with} / {total_tests_with}**"
    
    report_lines.append(f"| **TOTAL** | | {total_no_delta_str} | {total_delta_str} | {total_test_sav_str} | **{total_time_without:.2f}s** | **{total_time_with:.2f}s** | {total_time_sav_str} |")

    markdown_report = "\n".join(report_lines)
    print(markdown_report)
    
    # Save report to a file
    report_file = repo_root / "delta_benchmark_report.md"
    report_file.write_text(markdown_report)
    print(f"\nReport saved to: {report_file}")

if __name__ == "__main__":
    main()
