#!/bin/sh
# Script to sign a Scrapy release. To be run from root dir in Scrapy
# distribution.

cd dist
md5sum Scrapy-* > MD5SUMS
sha1sum Scrapy-* > SHA1SUMS
gpg -ba MD5SUMS
gpg -ba SHA1SUMS

# list files created
ls -l
