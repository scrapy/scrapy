#!/bin/sh
# Script to build a Scrapy release. To be run from root dir in Scrapy
# distribution.

# clean repo
hg purge --all

# build packages
version=$(python -c "import scrapy; print scrapy.__version__")
python setup.py sdist
# FIXME: bdist_wininst doesn't work on Unix (it doesn't include the data_files)
# To build the win32 release you need to use Windows for now.
#python setup.py bdist_wininst -t "Scrapy $version" -p "win32"

