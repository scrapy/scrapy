import os
import coverage

# Start coverage first as configured
coverage.process_startup()

# If started, set the context to the active test name
cov = coverage.Coverage.current()
if cov:
    test_name = os.environ.get("DELTA_TEST_NAME")
    if test_name:
        cov.switch_context(test_name)
