# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
from collections.abc import Sequence
from pathlib import Path

# If your extensions are in another directory, add it here. If the directory
# is relative to the documentation root, use Path.absolute to make it absolute.
sys.path.append(str(Path(__file__).parent / "_ext"))
sys.path.insert(0, str(Path(__file__).parent.parent))


# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Scrapy"
project_copyright = "Scrapy developers"
author = "Scrapy developers"


# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "notfound.extension",
    "scrapydocs",
    "sphinx.ext.autodoc",
    "scrapyfixautodoc",  # Must be after "sphinx.ext.autodoc"
    "sphinx.ext.coverage",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_rtd_dark_mode",
]

templates_path = ["_templates"]
exclude_patterns = ["build", "Thumbs.db", ".DS_Store"]

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# The short X.Y version.
try:
    import scrapy

    version = ".".join(map(str, scrapy.version_info[:2]))
    release = scrapy.__version__
except ImportError:
    version = ""
    release = ""

suppress_warnings = ["epub.unknown_project_files"]


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

html_last_updated_fmt = "%b %d, %Y"

html_css_files = [
    "custom.css",
]

# Set canonical URL from the Read the Docs Domain
html_baseurl = os.environ.get("READTHEDOCS_CANONICAL_URL", "")

# -- Options for LaTeX output ------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-latex-output

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author, document class [howto/manual]).
latex_documents = [
    ("index", "Scrapy.tex", "Scrapy Documentation", "Scrapy developers", "manual"),
]


# -- Options for the linkcheck builder ---------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-the-linkcheck-builder

linkcheck_ignore = [
    r"http://localhost:\d+",
    "http://hg.scrapy.org",
    r"https://github.com/scrapy/scrapy/commit/\w+",
    r"https://github.com/scrapy/scrapy/issues/\d+",
]

linkcheck_anchors_ignore_for_url = ["https://github.com/pyca/cryptography/issues/2692"]

# -- Options for the Coverage extension --------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/coverage.html#configuration

coverage_ignore_pyobjects = [
    # Contract’s add_pre_hook and add_post_hook are not documented because
    # they should be transparent to contract developers, for whom pre_hook and
    # post_hook should be the actual concern.
    r"\bContract\.add_(pre|post)_hook$",
    # ContractsManager is an internal class, developers are not expected to
    # interact with it directly in any way.
    r"\bContractsManager\b$",
    # For default contracts we only want to document their general purpose in
    # their __init__ method, the methods they reimplement to achieve that purpose
    # should be irrelevant to developers using those contracts.
    r"\w+Contract\.(adjust_request_args|(pre|post)_process)$",
    # Methods of downloader middlewares are not documented, only the classes
    # themselves, since downloader middlewares are controlled through Scrapy
    # settings.
    r"^scrapy\.downloadermiddlewares\.\w*?\.(\w*?Middleware|DownloaderStats)\.",
    # Base classes of downloader middlewares are implementation details that
    # are not meant for users.
    r"^scrapy\.downloadermiddlewares\.\w*?\.Base\w*?Middleware",
    # The interface methods of duplicate request filtering classes are already
    # covered in the interface documentation part of the DUPEFILTER_CLASS
    # setting documentation.
    r"^scrapy\.dupefilters\.[A-Z]\w*?\.(from_settings|request_seen|open|close|log)$",
    # Private exception used by the command-line interface implementation.
    r"^scrapy\.exceptions\.UsageError",
    # Methods of BaseItemExporter subclasses are only documented in
    # BaseItemExporter.
    r"^scrapy\.exporters\.(?!BaseItemExporter\b)\w*?\.",
    # Extension behavior is only modified through settings. Methods of
    # extension classes, as well as helper functions, are implementation
    # details that are not documented.
    r"^scrapy\.extensions\.[a-z]\w*?\.[A-Z]\w*?\.",  # methods
    r"^scrapy\.extensions\.[a-z]\w*?\.[a-z]",  # helper functions
    # Never documented before, and deprecated now.
    r"^scrapy\.linkextractors\.FilteringLinkExtractor$",
    # Implementation detail of LxmlLinkExtractor
    r"^scrapy\.linkextractors\.lxmlhtml\.LxmlParserLinkExtractor",
]


# -- Options for the InterSphinx extension -----------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html#configuration

intersphinx_mapping = {
    "attrs": ("https://www.attrs.org/en/stable/", None),
    "coverage": ("https://coverage.readthedocs.io/en/latest", None),
    "cryptography": ("https://cryptography.io/en/latest/", None),
    "cssselect": ("https://cssselect.readthedocs.io/en/latest", None),
    "itemloaders": ("https://itemloaders.readthedocs.io/en/latest/", None),
    "parsel": ("https://parsel.readthedocs.io/en/latest/", None),
    "pytest": ("https://docs.pytest.org/en/latest", None),
    "python": ("https://docs.python.org/3", None),
    "sphinx": ("https://www.sphinx-doc.org/en/master", None),
    "tox": ("https://tox.wiki/en/latest/", None),
    "twisted": ("https://docs.twisted.org/en/stable/", None),
    "twistedapi": ("https://docs.twisted.org/en/stable/api/", None),
    "w3lib": ("https://w3lib.readthedocs.io/en/latest", None),
}
intersphinx_disabled_reftypes: Sequence[str] = []

# -- Other options ------------------------------------------------------------
default_dark_mode = False
