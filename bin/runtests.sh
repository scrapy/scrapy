#!/bin/sh

# look for twisted trial command in common known locations
if [ -x /usr/bin/trial ]; then
    trial="/usr/bin/trial"
elif [ -x /usr/lib64/twisted/bin/trial ]; then
    trial="/usr/lib64/twisted/bin/trial"
fi

# disable custom settings for running tests in a neutral environment
export SCRAPY_SETTINGS_DISABLED=1

if [ $# -eq 0 ]; then
    $trial scrapy
else
    $trial "$@"
fi

