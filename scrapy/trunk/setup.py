from setuptools import setup, find_packages
import os, os.path, glob

def findfiles(pattern, base='.'):
    matches = []
    for root, _, _ in os.walk(base):
        matches.extend(glob.glob(os.path.join(root, pattern)))
    return matches


name = 'scrapy'

setup(
    name = name,
    version = '0.1',
    description = '',
    long_description = '',
    author = '',
    author_email = '',
    license = '',
    url = 'http://scrapy.org',

    packages = find_packages(),
    package_data = {
        '': ['*.tmpl'],
    },
    scripts = ['scrapy/bin/scrapy-admin.py'],
)
