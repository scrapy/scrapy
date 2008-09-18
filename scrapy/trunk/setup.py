from setuptools import setup, find_packages
import os, os.path, glob

def findfiles(pattern, base='.'):
    matches = []
    for root, _, _ in os.walk(base):
        matches.extend(glob.glob(os.path.join(root, pattern)))
    return matches


name = 'scrapy'

setup (
    name = name,
    version = '0.1',
    description = '',
    long_description = '',
    author = '',
    author_email = '',
    license = '',
    url = 'http://scrapy.org',

    packages = [name] + ['%s.%s' % (name,p) for p in find_packages('scrapy')],
    package_data = {name:
        findfiles('*.tmpl', 'scrapy/templates')
    },
    data_files = [],
    scripts = ['scrapy/bin/scrapy-admin.py'],
)
