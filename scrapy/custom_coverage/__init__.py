import sys
import json
import os
from pathlib import Path

class Coverage:
    def __init__(self):
        self.coverage_data = {
            "initiate_request": {"if": False,"else": False},
            "window_updated": {"if": False, "else": False}}
        
    def track_branch(self, function_name, branch):
        if function_name not in self.coverage_data:
            self.coverage_data[function_name] = {"if": False, "else": False}
        self.coverage_data[function_name][branch] = True

    def save_coverage_to_file(self):
        project_dir = Path(__file__).resolve().parent.parent.parent
        output_file = os.path.join(project_dir, "coverage_data.json")

        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                existing_data = json.load(f)
                for function_name, branches in self.coverage_data.items():
                    if function_name in existing_data:
                        for branch, hit in branches.items():
                            if hit:
                                existing_data[function_name][branch] = True
                    else:
                        existing_data[function_name] = branches
        else:
            existing_data = self.coverage_data

        with open(output_file, 'w') as f:
            json.dump(existing_data, f)
        
                

    def load_coverage(self, filepath):
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
        return {}

    def calculate_coverage(self, function_name):
        branches = self.coverage_data.get(function_name, {})
        total_branches = len(branches)
        covered_branches = sum(1 for hit in branches.values() if hit)
        coverage_percentage = (covered_branches / total_branches) * 100 if total_branches > 0 else 100
        return total_branches, covered_branches, coverage_percentage

    def report(self):
        report_lines = []

        for function, branches in self.coverage_data.items():
            total_branches, covered_branches, coverage_percentage = self.calculate_coverage(function)
            report_lines.append(f"{function}:")
            for branch, hit in branches.items():
                status = "hit" if hit else "not hit"
                report_lines.append(f"  {branch} branch was {status}")
            report_lines.append(f"  Total branches: {total_branches}")
            report_lines.append(f"  Covered branches: {covered_branches}")
            report_lines.append(f"  Coverage percentage: {coverage_percentage:.2f}%\n")

        return "\n".join(report_lines)

coverage = Coverage()

def print_coverage_report():
    project_dir = Path(__file__).resolve().parent.parent.parent
    output_file = os.path.join(project_dir, "coverage_data.json")
    coverage_data = coverage.load_coverage(output_file)
    if coverage_data:
        coverage.coverage_data = coverage_data
    print(coverage.report())

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: main.py report")
    else:
        command = sys.argv[1]
        if command == "report":
            print_coverage_report()
        else:
            print("Unknown command:", command)