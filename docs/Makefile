#
# Makefile for Scrapy documentation [based on Python documentation Makefile]
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#

# You can set these variables from the command line.
PYTHON       = python
SPHINXOPTS   =
PAPER        =
SOURCES      =

ALLSPHINXOPTS = -b $(BUILDER) -d build/doctrees -D latex_paper_size=$(PAPER) \
                $(SPHINXOPTS) . build/$(BUILDER) $(SOURCES)

.PHONY: help update build html htmlhelp clean

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  html      to make standalone HTML files"
	@echo "  htmlhelp  to make HTML files and a HTML help project"
	@echo "  latex     to make LaTeX files, you can set PAPER=a4 or PAPER=letter"
	@echo "  text      to make plain text files"
	@echo "  changes   to make an overview over all changed/added/deprecated items"
	@echo "  linkcheck to check all external links for integrity"


build: 
	mkdir -p build/$(BUILDER) build/doctrees
	sphinx-build $(ALLSPHINXOPTS)
	@echo


html: BUILDER = html
html: build
	@echo "Build finished. The HTML pages are in build/html."

htmlhelp: BUILDER = htmlhelp
htmlhelp: build
	@echo "Build finished; now you can run HTML Help Workshop with the" \
	      "build/htmlhelp/pydoc.hhp project file."

latex: BUILDER = latex
latex: build
	@echo "Build finished; the LaTeX files are in build/latex."
	@echo "Run \`make all-pdf' or \`make all-ps' in that directory to" \
	      "run these through (pdf)latex."

text: BUILDER = text
text: build
	@echo "Build finished; the text files are in build/text."

changes: BUILDER = changes
changes: build
	@echo "The overview file is in build/changes."

linkcheck: BUILDER = linkcheck
linkcheck: build
	@echo "Link check complete; look for any errors in the above output " \
	      "or in build/$(BUILDER)/output.txt"

doctest: BUILDER = doctest
doctest: build
	@echo "Testing of doctests in the sources finished, look at the " \
	      "results in build/doctest/output.txt"

pydoc-topics: BUILDER = pydoc-topics
pydoc-topics: build
	@echo "Building finished; now copy build/pydoc-topics/pydoc_topics.py " \
	      "into the Lib/ directory"

htmlview: html
	 $(PYTHON) -c "import webbrowser; webbrowser.open('build/html/index.html')"

clean:
	-rm -rf build/*

