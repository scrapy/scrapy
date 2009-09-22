#!/bin/sh
# Script to make a Scrapy release. To be run from root dir in Scrapy
# distribution.

# clean repo
hg purge --all

# build packages
#version=$(python -c "import scrapy; print scrapy.__version__")
#python setup.py sdist
# FIXME: bdist_wininst doesn't work on Unix (it doesn't include the data_files)
#python setup.py bdist_wininst -t "Scrapy $version" -p "win32"

# hash and sign
cd dist
md5sum scrapy-$version* > MD5SUMS
sha1sum scrapy-$version* > SHA1SUMS
gpg -ba MD5SUMS
gpg -ba SHA1SUMS

# list files created
ls -l
