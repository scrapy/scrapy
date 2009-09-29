#!/bin/sh
# Script to sign a Scrapy release. To be run from root dir in Scrapy
# distribution.

cd dist
md5sum scrapy-$version* > MD5SUMS
sha1sum scrapy-$version* > SHA1SUMS
gpg -ba MD5SUMS
gpg -ba SHA1SUMS

# list files created
ls -l
