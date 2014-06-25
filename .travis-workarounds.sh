#!/bin/bash
set -e
set -x

if [[ "${TOXENV}" == "pypy" ]]; then
    sudo add-apt-repository -y ppa:pypy/ppa
    sudo apt-get -qy update
    sudo apt-get install -y pypy pypy-dev
    # This is required because we need to get rid of the Travis installed PyPy
    # or it'll take precedence over the PPA installed one.
    sudo rm -rf /usr/local/pypy/bin
fi

# Workaround travis-ci/travis-ci#2065
pip install -U wheel
