import sys

from os.path import dirname, join
from setuptools import setup, find_packages

# --------------------------------------------------------------------------
# Fix requirements
# --------------------------------------------------------------------------
if sys.version_info[0] == 2:
    requirements_file = "requirements.txt"
else:
    requirements_file = "requirements-py3.txt"
with open(join(dirname(__file__), requirements_file), 'r') as f:
    requirements = [x.replace("\n", "") for x in f.readlines()]


with open(join(dirname(__file__), 'scrapy/VERSION'), 'rb') as f:
    version = f.read().decode('ascii').strip()


setup(
    name='Scrapy',
    version=version,
    url='http://scrapy.org',
    description='A high-level Web Crawling and Web Scraping framework',
    long_description=open('README.rst').read(),
    author='Scrapy developers',
    maintainer='Pablo Hoffman',
    maintainer_email='pablo@pablohoffman.com',
    license='BSD',
    packages=find_packages(exclude=('tests', 'tests.*')),
    include_package_data=True,
    zip_safe=False,
    entry_points={
        'console_scripts': ['scrapy = scrapy.cmdline:execute']
    },
    classifiers=[
        'Framework :: Scrapy',
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    install_requires=requirements,
)
