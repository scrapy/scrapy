from setuptools import setup, find_packages
import os, os.path, glob

def findfiles(pattern, base='.'):
    matches = []
    for root, _, _ in os.walk(base):
        matches.extend(glob.glob(os.path.join(root, pattern)))
    return matches


setup(
    name = 'scrapy',
    version = '0.8',
    description = '',
    long_description = '',
    author = '',
    author_email = '',
    license = '',
    url = 'http://scrapy.org',

    packages = find_packages(),
    package_data = {
        'scrapy': ['templates/*.tmpl'],
    },
    scripts = ['scrapy/bin/scrapy-admin.py'],
)
