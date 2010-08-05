#!/bin/sh

# look for twisted trial command
if type trial >/dev/null 2>&1; then
    trial="trial"
elif [ -x /usr/lib/twisted/bin/trial ]; then
    trial="/usr/lib/twisted/bin/trial"
elif [ -x /usr/lib64/twisted/bin/trial ]; then
    trial="/usr/lib64/twisted/bin/trial"
else
    echo "Unable to run tests: trial command (included with Twisted) not found"
    exit 1
fi


# disable custom settings for running tests in a neutral environment
export SCRAPY_SETTINGS_DISABLED=1

find -name '*.py[co]' -delete
if [ $# -eq 0 ]; then
    $trial scrapy
else
    $trial "$@"
fi

