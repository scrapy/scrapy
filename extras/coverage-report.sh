#!/bin/sh
# Run tests, generate coverage report and open it in a browser
#
# Requires: coverage 3.3 or above from http://pypi.python.org/pypi/coverage

trial="`which trial`"
# use the first coverage command found in the path
coverage="`which coverage`"
[ ! $? -eq 0 ] && coverage="`which python-coverage`"  # debian's executable
[ ! $? -eq 0 ] && coverage="`which python3-coverage`" # debian's py3 executable

if [ -z "$coverage" ] || [ -z "$trial" ]; then
	echo "coverage or trial commands were not found on your system, aborting."
fi

$coverage run --branch $trial --reporter=text tests
$coverage html -i
python -m webbrowser htmlcov/index.html
