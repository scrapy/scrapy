from pathlib import Path

from setuptools import find_packages, setup

version = (Path(__file__).parent / "scrapy/VERSION").read_text("ascii").strip()


install_requires = [
    "Twisted>=21.7.0",
    "cryptography>=37.0.0",
    "cssselect>=0.9.1",
    "itemloaders>=1.0.1",
    "parsel>=1.5.0",
    "pyOpenSSL>=22.0.0",
    "queuelib>=1.4.2",
    "service_identity>=18.1.0",
    "w3lib>=1.17.0",
    "zope.interface>=5.1.0",
    "protego>=0.1.15",
    "itemadapter>=0.1.0",
    "packaging",
    "tldextract",
    "lxml>=4.6.0",
    "defusedxml>=0.7.1",
]
extras_require = {
    ':platform_python_implementation == "CPython"': ["PyDispatcher>=2.0.5"],
    ':platform_python_implementation == "PyPy"': ["PyPyDispatcher>=2.1.0"],
}


setup(
    name="Scrapy",
    version=version,
    url="https://scrapy.org",
    project_urls={
        "Documentation": "https://docs.scrapy.org/",
        "Source": "https://github.com/scrapy/scrapy",
        "Tracker": "https://github.com/scrapy/scrapy/issues",
    },
    description="A high-level Web Crawling and Web Scraping framework",
    long_description=open("README.rst", encoding="utf-8").read(),
    author="Scrapy developers",
    author_email="pablo@pablohoffman.com",
    maintainer="Pablo Hoffman",
    maintainer_email="pablo@pablohoffman.com",
    license="BSD",
    packages=find_packages(exclude=("tests", "tests.*")),
    include_package_data=True,
    zip_safe=False,
    entry_points={"console_scripts": ["scrapy = scrapy.cmdline:execute"]},
    classifiers=[
        "Framework :: Scrapy",
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.9",
    install_requires=install_requires,
    extras_require=extras_require,
)
