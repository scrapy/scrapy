from os.path import dirname, join
from pkg_resources import parse_version
from setuptools import setup, find_packages, __version__ as setuptools_version


with open(join(dirname(__file__), 'scrapy/VERSION'), 'rb') as f:
    version = f.read().decode('ascii').strip()


def has_environment_marker_platform_impl_support():
    """Code extracted from 'pytest/setup.py'
    https://github.com/pytest-dev/pytest/blob/7538680c/setup.py#L31

    The first known release to support environment marker with range operators
    it is 18.5, see:
    https://setuptools.readthedocs.io/en/latest/history.html#id235
    """
    return parse_version(setuptools_version) >= parse_version('18.5')


install_requires = [
    'Twisted>=17.9.0',
    'cryptography>=2.0',
    'cssselect>=0.9.1',
    'itemloaders>=1.0.1',
    'parsel>=1.5.0',
    'PyDispatcher>=2.0.5',
    'pyOpenSSL>=16.2.0',
    'queuelib>=1.4.2',
    'service_identity>=16.0.0',
    'w3lib>=1.17.0',
    'zope.interface>=4.1.3',
    'protego>=0.1.15',
    'itemadapter>=0.1.0',
]
extras_require = {}

if has_environment_marker_platform_impl_support():
    extras_require[':platform_python_implementation == "CPython"'] = [
        'lxml>=3.5.0',
    ]
    extras_require[':platform_python_implementation == "PyPy"'] = [
        # Earlier lxml versions are affected by
        # https://foss.heptapod.net/pypy/pypy/-/issues/2498,
        # which was fixed in Cython 0.26, released on 2017-06-19, and used to
        # generate the C headers of lxml release tarballs published since then, the
        # first of which was:
        'lxml>=4.0.0',
        'PyPyDispatcher>=2.1.0',
    ]
else:
    install_requires.append('lxml>=3.5.0')


setup(
    name='Scrapy',
    version=version,
    url='https://scrapy.org',
    project_urls = {
        'Documentation': 'https://docs.scrapy.org/',
        'Source': 'https://github.com/scrapy/scrapy',
        'Tracker': 'https://github.com/scrapy/scrapy/issues',
    },
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
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    python_requires='>=3.6',
    install_requires=install_requires,
    extras_require=extras_require,
)
